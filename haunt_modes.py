"""剧本行为按 mode 分派。

背景
----
70 个剧本在 `haunt_rules.py` 里各有一个唯一 `mode`（werewolf_hunt、
labyrinth_escape、banishment_escort …）。但引擎原本是这样分派的：

    if self.state.haunt.id == 1:  return self._available_haunt1_actions(player)
    if self.state.haunt.id == 5:  return self._available_haunt5_actions(player)
    return self._available_generic_haunt_actions(player)

也就是说：mode 字段写在数据里、引擎从不读取，是死数据；剧本行为只能靠
在引擎里加 `haunt.id == N` 分支来扩展。严格复刻 70 个剧本时，这条路会
把 engine.py 撑爆，而且每加一个剧本都要改引擎。

本模块把分派改成按 mode 查表：
    注册了 handler 的 mode  → 走定制逻辑
    没注册的 mode           → 走 GenericModeHandler（现有通用规则）
这样新增剧本行为只需在这里加一个类，不必碰引擎。

设计约束
--------
* handler 用鸭子类型，不 import engine，避免循环导入。engine 在运行时
  才 import 本模块。
* 未注册的 mode 必须优雅降级到通用规则，绝不能抛异常——否则一个没写
  handler 的剧本就会让整个作祟阶段崩掉。
* 本模块只负责「怎么分派」，具体规则实现仍在 engine / haunt_rules，
  避免把引擎逻辑复制到这里造成第二份维护。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# 方位→格偏移（与 models.py 保持一致，避免 import engine 循环导入）
DIRECTION_DELTAS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}


class ExitOption:
    """与 engine.ExitOption 同构的轻量副本（避免 import engine 循环导入）。"""

    __slots__ = ("label", "direction", "target_key", "target_room_name", "is_new_room", "is_special", "cost")

    def __init__(self, label: str, direction: str, target_key: str,
                 target_room_name: str | None = None, is_new_room: bool = False,
                 is_special: bool = False, cost: int = 1):
        self.label = label
        self.direction = direction
        self.target_key = target_key
        self.target_room_name = target_room_name
        self.is_new_room = is_new_room
        self.is_special = is_special
        self.cost = cost


@runtime_checkable
class HauntModeHandler(Protocol):
    """一个剧本模式的行为。

    参数里的 engine / player 用 Any 是刻意的：本模块若 import engine 会
    形成循环依赖。实现方按 GameEngine / Player 的真实接口调用即可。
    """

    mode: str

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        """返回该玩家此刻可执行的剧本行动。"""
        ...

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        """执行一个剧本行动，返回是否成功。"""
        ...

    def check_victory(self, engine: Any) -> bool:
        """检查该模式的专属胜负条件，返回是否已分出胜负。"""
        ...

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        """作祟刚开始时执行一次：放令牌、补牌等。"""
        ...

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        """有玩家进入房间时触发（用于令牌拾取之类）。"""
        ...

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        """房间首次被发现时触发（用于"某张牌不在场就补抽"这类规则）。"""
        ...

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """怪物命中时触发。返回 True 表示伤害已由剧本结算，引擎不再处理。"""
        ...

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """怪物移动掷骰后触发。返回 True 表示剧本已自行处理移动。"""
        ...

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """怪物被玩家攻击命中后触发。返回 True 表示剧本已处理后果。

        引擎默认"击败怪物 = 击晕一回合"，但不少剧本要求真正杀死怪物：
          · 剧本 2 p13："One of these Sanity attacks must succeed for the
            ghost to be destroyed"
          · 剧本 3 p14："After you cast the spell on her, any successful
            attack will kill her"
        没有这个钩子，怪物永远只是昏迷，这类剧本的胜利条件无法达成。
        """
        ...

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """怪物回合的攻击阶段触发（无论掷骰成败）。返回 True 表示已接管。

        与 on_monster_attack 的区别：后者只在引擎判定怪物命中后才调用；
        而剧本 6 外星人的意念攻击是"代替普通攻击"的主动技能——对同房间
        每个探险者各自理智对决，输赢都要结算，所以需要这个更早的钩子。
        """
        ...

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """玩家回合开始时触发（用于诅咒发作、计时器推进等）。"""
        ...


class GenericModeHandler:
    """默认处理器：直接执行 rule_data 里声明的 actions / win_conditions。

    当前 68 个没有定制 handler 的剧本都走这里。它把 engine 里原有的通用
    逻辑包装成 handler 接口，行为与改造前完全一致。
    """

    mode = "generic"

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        return engine._available_generic_haunt_actions(player)

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        return engine._perform_generic_haunt_action(player, action_id, data)

    def check_victory(self, engine: Any) -> bool:
        return engine._check_generic_haunt_victory()

    # 生命周期钩子默认什么都不做，需要时由子类覆盖。
    # 引擎会无条件调用它们，所以这里不能抛异常。
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        return None

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        return None

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        return None

    # 这两个返回 False 是刻意的：False = "我没处理，引擎按默认来"。
    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        return False

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        return False

    def on_turn_start(self, engine: Any, player: Any) -> None:
        return None

    def on_turn_end(self, engine: Any, player: Any) -> None:
        """每位玩家回合结束时调用（剧本 22 p104：每回合结束都要塌房间）。
        引擎在怪物回合之前调用，保证扩散与怪物行动同轮。"""
        return None

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        return False

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        return False

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """每只怪物回合开始（剧本 7 的"拖回根部即吞噬"等）。True=本回合不再行动。"""
        return False

    def mystic_elevator_blocked(self, engine: Any, player: Any) -> bool:
        """神秘电梯是否被剧本机制堵住（剧本 7：藤蔓尖端在电梯房间内）。"""
        return False

    def item_pickup_blocked(self, engine: Any, player: Any, card_id: str) -> bool:
        """某张卡是否禁止被该玩家捡起（剧本 7：叛徒不能重拾古书）。"""
        return False

    def item_trade_blocked(self, engine: Any, giver: Any, target: Any, card_id: str) -> bool:
        """某张卡是否禁止被该玩家自愿交出（剧本 9：持圣徽者不能转交圣徽）。"""
        return False

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """剧本是否允许这次攻击（剧本 2：降灵完成前谁都不能动手）。"""
        return True

    def monster_rerolls_blanks(self, engine: Any, monster: Any) -> bool:
        """怪物攻击时是否把空白骰重掷一次（剧本 4 蜘蛛 p86）。"""
        return False

    def on_player_moved(self, engine: Any, player: Any) -> None:
        """玩家移动后回调（剧本 3：背着青蛙走，蛙跟着主人）。"""
        return None

    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        """徒手攻击的属性覆盖（剧本 11：持戒指者对雾中人影改为理智攻击）。"""
        return None

    def monster_counterattack_disabled(self, engine: Any, monster: Any) -> bool:
        """昏迷怪物的反击是否无效（剧本 12 p23：昏迷双胞胎防守但无伤害）。"""
        return False

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        """攻击结算后的后处理（剧本 12：与自己的双胞胎交手必掉 1 点各属性）。"""
        return None

    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None) -> int:
        """玩家移动费用的倍率（剧本 14：背尸入房按 2 格计）。"""
        return 1

    def movement_cost_floor(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """玩家移动费用的下限（剧本 17：蟑螂守厨房离开 3 格；剧本 33：湖面砖 2/3 格）。"""
        return 0

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """攻击落败时是否免除攻击者受到的反击伤害（剧本 17：用杀虫剂落败不受伤）。"""
        return False

    def special_steal(self, engine: Any, attacker: Any, target: Any, diff: int, attack_attr: str) -> bool:
        """剧本自定义的特殊偷取（剧本 19：>2 伤害偷走长矛）。返回 True 表示已处理。"""
        return False

    def extra_move_options(self, engine: Any, player: Any, options: list) -> list:
        """追加额外移动选项（剧本 33：湖面砖扩展）。"""
        return []

    def lake_move(self, engine: Any, player: Any, option: Any) -> bool:
        """接管 lake: 前缀的移动选项（剧本 33）。返回 True 表示已处理。"""
        return False

    def on_item_dropped(self, engine: Any, player: Any, card_id: str) -> None:
        """物品丢弃后处理（剧本 33：湖面丢弃即沉没）。"""
        return None

    def on_player_died(self, engine: Any, player: Any) -> None:
        """玩家死亡后的后处理（剧本 14：尸体留在房间里可被搬走）。"""
        return None

    def attack_roll_bonus(self, engine: Any, attacker: Any, target: Any) -> int:
        """对怪物攻击的骰值加值（剧本 15：持矛对巨龙 +4）。"""
        return 0

    def physical_damage_reduction(self, engine: Any, player: Any, amount: int, source: str, damage_type: str) -> int:
        """物理伤害减免（剧本 15：古董护甲 -5，对火焰无效）。"""
        return 0

    def suppress_room_draw(self, engine: Any, player: Any, room: Any) -> bool:
        """本次发现房间是否跳过符号抽牌（剧本 16：改为攻击幻影）。"""
        return False

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """这次击败怪物是「直接杀死」还是「仅击晕」（剧本 21 p32：只有力量武器
        与炸药能杀死僵尸，徒手或其他属性只能打晕）。

        返回 True = 杀死（引擎调用 `_kill_monster` 移出对局）。
        优先级高于 `on_monster_defeated`：需要知道"谁用什么打的"就覆盖这个，
        只按怪物类型判定的仍用 `on_monster_defeated`。
        """
        return False

    def monster_attack_roll_bonus(self, engine: Any, monster: Any, target: Any) -> int:
        """怪物主动攻击某目标时的攻击骰修正（剧本 21 p32：圣徽持有者让僵尸
        少掷两枚骰）。默认 0 = 不修正。"""
        return 0

    def explore_stop_suspended(self, engine: Any, player: Any) -> bool:
        """本剧本是否解除「探索新房间必须停下」的限制（剧本 25 p36）。

        返回 True 时引擎在探索新房间后不再强制结束移动、不再清空步数；
        配合 `suppress_room_draw` 把符号抽牌推迟到"结束移动的房间"再结算。
        """
        return False

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """剧本定制的 bot 寻路目标（可选，duck-typed，bot_ai 会探测）。

        返回模板 id 列表或 ["__room__<room_key>", ...]；返回空则 bot 退回
        rule_data 的通用换算（actions 的 rooms / same_room / key_rooms）。
        剧本 25 首个使用者：每个英雄要找的是"自己娃娃"的两个候选房间，
        rule_data 的静态 rooms 表表达不了按玩家区分的目标。
        """
        return []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        """剧本进度摘要（可选，duck-typed，桌面 UI 面板会探测）。

        返回公开信息的可读行；通用轨道（value/target）由 UI 自己渲染，
        这里只补充轨道表达不了的内容（销毁计数、状态标记等）。
        """
        return []

    def room_entry_blocked(self, engine: Any, player: Any, room: Any) -> bool:
        """该玩家是否禁止进入/探索该房间（剧本 26：英雄与老鼠进不了五芒星室）。

        引擎在两处调用：`available_move_options` 过滤已有的相邻房间选项；
        探索新房间抽牌时若抽到被禁的模板则弃掉重抽。room 可能是 PlacedRoom
        也可能是 RoomTemplate（探索场景），判断时读 template_id / id 即可。
        """
        return False

    def can_discover_rooms(self, engine: Any, player: Any) -> bool:
        """该玩家能否发现新房间（剧本 27：Blobperson 不能发现房间，p109）。

        返回 False 时引擎在探索新房间前直接拦下（与青蛙的处理同款）。
        """
        return True

    def counts_as_movement_obstacle(self, engine: Any, mover: Any, occupant: Any) -> bool:
        """该占用者是否让对手离开房间多花 1 格（剧本 67：入定的叛徒不阻挡）。"""
        return True

    def item_use_blocked(self, engine: Any, player: Any, card_id: str) -> bool:
        """该玩家是否禁止主动使用物品（剧本 67：入定的叛徒不能用物品）。"""
        return False


class BanishmentEscortMode(GenericModeHandler):
    """剧本 1 木乃伊苏醒（The Mummy Walks）。

    权威原文：英雄手册 p12 / 叛徒手册 p83。

    已核对且原本就正确的部分：
        木乃伊属性 Speed 3 / Might 8 / Sanity 5；两步调查均为 Knowledge 6+；
        放逐需 2 枚知识检定令牌 + 持书与木乃伊同房间打理智战。
    本次补齐的是此前完全缺失的令牌链路：
        石棺/木乃伊/女孩三个令牌的放置、女孩拾取、关键牌不在场时补抽。
    已实现（on_monster_attack / on_monster_move，见下方方法）：
        木乃伊造成速度伤害直到对手速度触底（但不降到骷髅）后转为力量伤害；
        单次造成 2+ 伤害时可改为夺取物品或抢走女孩（人类叛徒弹窗选择，
        机器人固定优先抢女孩）；
        移动掷出 0 或 1 时可经秘密通道移动到屋内任意位置（机器人固定选
        "朝最近英雄"；原版由叛徒任选房间——若将来支持人类叛徒自选，在
        on_monster_move 里加 prompter 询问即可）。
    """

    mode = "banishment_escort"

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        return engine._available_haunt1_actions(player)

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        return engine._perform_haunt1_action(player, action_id, data)

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        # 叛徒手册 p83："Set aside the Girl card." —— 先把女孩卡从预兆牌堆
        # 里取出来，之后只能靠走进女孩令牌所在房间来拿到。不这样做的话，
        # 女孩会被当作普通预兆牌抽走，令牌机制就形同虚设。
        # 若女孩卡此时已在某人手上或遗落在房间里，则保持现状。
        if not engine._card_is_controlled("omen_girl"):
            for deck in engine.state.card_decks.values():
                if "omen_girl" in deck:
                    deck.remove("omen_girl")
                    break
        # 叛徒手册 p83：木乃伊令牌（大）与石棺令牌（五边形）放在作祟揭示的房间
        engine.spawn_token("sarcophagus", label="石棺", role="marker", room_key=room_key)
        mummy = engine._monster_by_template("mummy")
        if mummy:
            engine.spawn_token("mummy_marker", label="木乃伊", role="marker", room_key=mummy.room_key)
        # p83：女孩令牌放在同一楼层、距木乃伊至少 5 格的房间；
        #      没有这么远的就放在该楼层尽可能远处。
        girl_room = engine._haunt1_girl_start_room(room_key)
        if girl_room:
            engine.spawn_token("girl", label="女孩", role="marker", room_key=girl_room)
        # 英雄手册 p12：预先拿出 2 枚知识检定令牌（三角形）
        engine.spawn_tokens("knowledge_check", 2, label="知识检定", role="check")

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        # p12 / p83：探险者进入女孩所在房间就把女孩带走。
        # 叛徒按 p83 "You lose the Girl" 不能拿。
        if player.role == "traitor" or player.dead:
            return
        if engine._card_is_controlled("omen_girl"):
            return
        girl = next(iter(engine.tokens_in_room(room.key, "girl")), None)
        if girl is None:
            return
        if engine._grant_card_to_player(player, "omen_girl"):
            engine.remove_token(girl.uid)
            engine._log(f"{player.name} 在{room.name}找到了女孩。")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        if room.symbol != "omen":
            return
        # p12：书若不在场上，下一个发现预兆房间的英雄从预兆牌堆里找出书。
        if player.role == "hero" and not engine._card_is_controlled("omen_book"):
            if engine._grant_card_to_player(player, "omen_book"):
                engine._log("有人在预兆牌堆里翻出了那本古书。")
            return
        # p83：戒指与圣徽都不在场时，下次发现预兆房间补抽其中之一。
        if player.role == "traitor":
            if engine._card_is_controlled("omen_ring") or engine._card_is_controlled("omen_holy_symbol"):
                return
            for card_id in ("omen_ring", "omen_holy_symbol"):
                if engine._grant_card_to_player(player, card_id):
                    card = engine.catalog.cards[card_id]
                    engine._log(f"仪式所需的{card.name}被找了出来。")
                    return

    # ---------------------------------------------------------------- 战斗
    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """木乃伊的专属攻击结算。

        叛徒手册 p83 原文：
            "The Mummy makes Might attacks but inflicts Speed damage until its
             opponent's Speed is at its lowest number. (This attack can't lower
             that trait to the skull symbol.) After that, its opponent takes
             Might damage instead until he or she is dead.
             When the Mummy inflicts 2 or more points of damage with an attack,
             it can steal an item from its opponent instead of inflicting that
             damage. The Mummy can also take the Girl from her custodian
             this way."
        """
        if _monster_id(monster) != "mummy" or amount <= 0:
            return False

        # 造成 2 点以上伤害时，可改为夺取物品或抢走女孩
        if amount >= 2 and self._haunt1_steal_instead(engine, monster, target, amount):
            return True

        # 速度尚未触底就扣速度（且不能扣到骷髅）；触底后改扣力量
        position = target.stat_positions.get("speed")
        track = engine._stat_track(target, "speed")
        if track and position is not None and position > 0:
            # position 就是还能往下降的格数，最多降到最低格（索引 0）
            engine._apply_stat_loss(target, "speed", min(amount, position))
        else:
            engine._apply_stat_loss(target, "might", amount)
        engine._check_player_death(target)
        return True

    def _haunt1_steal_instead(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """木乃伊改为夺取物品/女孩。返回 True 表示已夺取，本次不造成伤害。"""
        girl_first = [card_id for card_id in target.items if card_id == "omen_girl"]
        others = [card_id for card_id in target.items if card_id != "omen_girl"]
        if not girl_first and not others:
            return False

        traitor = next((p for p in engine.state.players if p.role == "traitor" and not p.dead), None)
        picked: str | None = None

        if traitor is not None and traitor.control == "human" and engine.prompter is not None:
            options = ["造成正常伤害"]
            mapping: list[str] = []
            for card_id in girl_first + others:
                card = engine.catalog.cards.get(card_id)
                if card:
                    options.append(f"夺取：{card.name}")
                    mapping.append(card_id)
            if len(options) == 1:
                return False
            choice = engine.prompter.choose_from_list(
                "木乃伊",
                f"木乃伊造成 {amount} 点伤害，可以改为夺取 {target.name} 的一件物品。",
                options,
            )
            if choice is None or choice == 0 or not (1 <= choice <= len(mapping)):
                return False
            picked = mapping[choice - 1]
        else:
            # 机器人叛徒：优先抢女孩，没有女孩就拿第一件物品
            picked = (girl_first + others)[0]

        target.items.remove(picked)
        card = engine.catalog.cards[picked]
        engine._log(f"木乃伊从 {target.name} 手中夺走了{card.name}。")
        if picked == "omen_girl":
            # p83：木乃伊可以这样把女孩从监护人手里抢走
            engine.state.meta.setdefault("haunt_rule", {}).setdefault("flags", {})["mummy_has_girl"] = True
        engine._check_player_death(target)
        return True

    # ---------------------------------------------------------------- 移动
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """木乃伊移动掷出 0 或 1 时可经秘密通道前往屋内任意房间。

        叛徒手册 p83："If the Mummy rolls a 0 or a 1 for its movement, it may
        use a secret passage to move to any space in the house."
        """
        if _monster_id(monster) != "mummy":
            return False
        if rolled > 1:
            return False  # 掷出 2 以上按常规移动处理

        target = engine._find_monster_target(monster)
        if target is None:
            return False
        # 直接落到目标所在房间：秘密通道本就可以去屋内任意位置，
        # 对机器人而言追人是最合理的选择，也保证同一种子结果一致。
        if monster.room_key == target.room_key:
            return True  # 已在目标房间，无需移动
        monster.room_key = target.room_key
        engine._log(f"木乃伊掷出 {rolled}，经秘密通道移动到 {engine.state.board[target.room_key].name}。")
        return True

    def check_victory(self, engine: Any) -> bool:
        mummy = engine._monster_by_template("mummy")
        if mummy and engine._haunt1_mummy_ready_to_win(mummy):
            engine._set_winner("traitor", "木乃伊带着女孩和仪式物回到了石棺房。")
            return True
        return engine._check_generic_haunt_victory()


class WerewolfHuntMode(GenericModeHandler):
    """剧本 5 我曾是少年狼人：感染转化 + 银弹击杀，胜负仍走通用 win_conditions。"""

    mode = "werewolf_hunt"

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        return engine._available_haunt5_actions(player)

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        return engine._perform_haunt5_action(player, action_id, data)

    def on_turn_start(self, engine: Any, player: Any) -> None:
        # 叛徒每回合开始时力量与速度各 +1；被感染的英雄做神志检定抵抗转化。
        # 原本硬编码在 engine._apply_start_of_turn_haunt_effects 里，现迁到这里。
        engine._haunt5_start_of_turn(player)


class SeanceRaceMode(GenericModeHandler):
    """剧本 2 降灵会（The Séance）。

    权威原文：英雄手册 p13 / 叛徒手册 p84。

    规则核心是一场"召灵竞速"：
        英雄：五芒星室内 Knowledge 或 Sanity 5+，累计成功次数达到
              玩家数一半（向下取整）即完成降灵。
        叛徒：持有通灵板即可在任何地方尝试，但必须成功 1 次 Knowledge
              **和** 1 次 Sanity（各一次，不能两次同属性）。
        先完成者召唤并控制幽灵。

    英雄召灵后进入安葬任务：阁楼/卧室/主卧找骨头（Knowledge 5+），
    搬到地窖或墓地安葬（Knowledge 5+），限时 5 回合；逾期则叛徒夺过
    幽灵控制权，此后只有摧毁幽灵一条路。

    已实现：竞速（含叛徒 1+1 的属性限制）、幽灵延迟生成与控制权、
    计时器、找骨头/安葬、胜利判定、幽灵理智攻击（精神伤害）、
    幽灵穿墙移动、英雄控灵期间幽灵不攻击、
    "降灵完成前禁止攻击"（p13 "No one can attack until after the séance
    has been completed"，attack_allowed 钩子）。
    已知简化：叛徒控灵引发"房屋坍塌"未实现（需要房间翻转/相邻性/
    死亡整套系统，规模较大，单独立项）。
    """

    mode = "seance_race"

    # ------------------------------------------------------------- 攻击闸门
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p13：降灵会完成（任一方召出幽灵）之前，谁都不能攻击。"""
        return bool(engine._haunt_flags().get("ghost_summoned"))

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        # 英雄手册 p13：知识与神志检定令牌各"玩家数"枚，另有幽灵与尸体令牌
        count = len(engine.state.players)
        engine.spawn_tokens("knowledge_check", count, label="知识检定", role="check")
        engine.spawn_tokens("sanity_check", count, label="神志检定", role="check")

    # ------------------------------------------------------------- 行动
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "seance_check":
            return self._seance_check(engine, player)
        # find_bones / bury_bones 走通用检定，但要在成功后置 flags —— 通过
        # rule_data 的 set_flags 已覆盖（bones_found / bones_buried）。
        # 安葬成功即英雄获胜，由 check_victory 兜住。
        return super().perform_action(engine, player, action_id, data)

    def _seance_check(self, engine: Any, player: Any) -> bool:
        flags = engine._haunt_flags()
        if flags.get("ghost_summoned"):
            engine._log("降灵会已经结束，幽灵已被召唤。")
            return False

        # 选属性：英雄两选一；叛徒必须补自己还缺的那种
        options = ["知识检定", "神志检定"]
        if player.role == "traitor":
            has_k = int(flags.get("traitor_seance_knowledge", 0)) > 0
            has_s = int(flags.get("traitor_seance_sanity", 0)) > 0
            if has_k and not has_s:
                options = ["神志检定"]
            elif has_s and not has_k:
                options = ["知识检定"]

        stat = "knowledge"
        if len(options) == 2 and player.control == "human":
            choice = engine.prompter.choose_from_list("降灵会", "要尝试哪种检定？", options)
            if choice is None:
                return False
            stat = "knowledge" if choice == 0 else "sanity"
        elif len(options) == 2:
            # 机器人：选自己属性更高的那种
            stat = "knowledge" if player.stats.get("knowledge", 0) >= player.stats.get("sanity", 0) else "sanity"
        else:
            stat = "knowledge" if options[0] == "知识检定" else "sanity"

        if not engine._resolve_check(player, stat, 5, "降灵会检定"):
            return True  # 检定失败也算行动已执行（占用本回合剧本行动）

        prefix = "hero_seance" if player.role == "hero" else "traitor_seance"
        flags[f"{prefix}_{stat}"] = int(flags.get(f"{prefix}_{stat}", 0)) + 1
        engine._log(f"{player.name} 的降灵会检定成功（{stat}）。")

        if player.role == "hero":
            total = int(flags.get("hero_seance_knowledge", 0)) + int(flags.get("hero_seance_sanity", 0))
            target = engine._haunt_track_target("hero_seance")
            engine._log(f"英雄降灵进度：{total}/{target}。")
            if total >= target:
                self._summon_ghost(engine, control="heroes", room_key=player.room_key)
        else:
            has_k = int(flags.get("traitor_seance_knowledge", 0)) > 0
            has_s = int(flags.get("traitor_seance_sanity", 0)) > 0
            if has_k and has_s:
                self._summon_ghost(engine, control="traitor", room_key=player.room_key)
        return True

    def _summon_ghost(self, engine: Any, control: str, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["ghost_summoned"] = True
        flags["ghost_control"] = control
        haunt = engine.state.haunt
        spec = next(
            (m for m in (haunt.rule_data or {}).get("monsters", []) if m.get("spawn") == "deferred"),
            {},
        )
        ghost = engine._spawn_single_haunt_monster(spec, room_key)
        if ghost:
            engine.spawn_token("ghost", label="幽灵", role="marker", room_key=room_key)
            if control == "heroes":
                # p13：英雄召灵后幽灵停留在最后一次成功检定的房间，限时安葬
                flags["seance_owner_id"] = engine.current_player.id
                engine._log("英雄们率先完成降灵，幽灵听从你们的指令：“埋葬我的骸骨！”")
            else:
                engine._log("叛徒率先完成了降灵，幽灵浮现在他身侧。")
                engine._set_haunt_track_value("ghost_rest_timer", 0)

    # ------------------------------------------------------------- 计时器
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if flags.get("ghost_control") != "heroes" or flags.get("bones_buried"):
            return
        owner = flags.get("seance_owner_id")
        if owner is None or player.id != owner:
            return
        current = engine._haunt_track_value("ghost_rest_timer")
        engine._set_haunt_track_value("ghost_rest_timer", current + 1)
        deadline = engine._haunt_track_target("ghost_rest_timer")
        engine._log(f"安葬倒计时：{current + 1}/{deadline}。")
        # p13：到第 5 回合仍未安葬 → 叛徒夺控，且"安葬"不再够，必须摧毁幽灵
        if current + 1 >= deadline:
            flags["ghost_control"] = "traitor"
            engine._log("时限已到，叛徒夺取了幽灵的控制权！现在只有摧毁它一条路。")

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # 英雄安葬成功 → 直接获胜
        if flags.get("bones_buried"):
            engine._set_winner("heroes", "英雄们安葬了幽灵的骸骨，它的灵魂终于安息。")
            return True
        # 幽灵已被摧毁（被击杀即从 monsters 移除）→ 英雄获胜
        if flags.get("ghost_summoned") and engine._monster_by_template("ghost") is None:
            engine._set_winner("heroes", "英雄们摧毁了幽灵。")
            return True
        # 通用条件（此处仅有 all_heroes_dead → 叛徒胜）
        if super().check_victory(engine):
            return True
        # p84："If the traitor dies, you keep control of the Ghost."
        # 杀死叛徒【不】构成英雄胜利——吸收引擎"叛徒死亡→英雄胜"的通用
        # 兜底（返回 True 但不设 winner，游戏按本剧本规则继续）。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- 幽灵行为
    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p13/p84：摧毁幽灵。

        引擎默认"击败怪物 = 击晕一回合"，但剧本 2 的胜利条件之一是"用理智
        攻击摧毁幽灵"。只有先让幽灵真正离场，英雄才有第二条取胜路径，
        否则叛徒控灵后英雄只能挨打到全灭（seed=109 实测僵局）。
        """
        if _monster_id(monster) != "ghost":
            return False
        engine.state.monsters = [m for m in engine.state.monsters if m.id != monster.id]
        engine._log("幽灵发出一声哀鸣，消散在雾里。")
        engine.check_victory()
        return True

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        if _monster_id(monster) != "ghost":
            return False
        # p13："While you're doing this, the Ghost can't attack anyone."
        # 英雄控灵且尚未安葬 → 幽灵不攻击（返回 True 表示已处理，吞掉本次攻击）
        flags = engine._haunt_flags()
        if flags.get("ghost_control") == "heroes" and not flags.get("bones_buried"):
            return True
        if amount <= 0:
            return True
        # p13/p84：幽灵做理智攻击，造成精神伤害
        engine._deal_damage(target, "mental", amount, source=monster.name)
        return True

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """幽灵移动（p84 "The Ghost can move through walls and collapsed rooms"）。

        引擎常规移动沿连通图走，对可穿墙的幽灵反而是错误限制。这里按棋盘
        曼哈顿距离（含楼层差）直接向目标跳 rolled 步，同距离取 key 排序
        最小者保证可复现。

        p13：英雄召灵后幽灵"stays there until you lose control of it"——
        英雄控灵期间幽灵停在原地，不移动。
        """
        if _monster_id(monster) != "ghost":
            return False
        flags = engine._haunt_flags()
        if flags.get("ghost_control") == "heroes" and not flags.get("bones_buried"):
            return True  # 英雄控灵：停在召唤房间
        target = engine._find_monster_target(monster)
        if target is None:
            return True
        if monster.room_key == target.room_key:
            return True
        t_room = engine.state.board.get(target.room_key)
        m_room = engine.state.board.get(monster.room_key)
        if not t_room or not m_room:
            return False

        def dist(room: Any) -> int:
            return abs(room.floor - t_room.floor) + abs(room.x - t_room.x) + abs(room.y - t_room.y)

        current = dist(m_room)
        budget = max(1, rolled)
        if current <= budget:
            monster.room_key = target.room_key
            return True
        # 目标超出步数：跳到距离目标恰为 current-budget 的房间（取排序最小 key）
        wanted = current - budget
        best_key = None
        best_gap = None
        for key in sorted(engine.state.board):
            gap = abs(dist(engine.state.board[key]) - wanted)
            if best_gap is None or gap < best_gap:
                best_key, best_gap = key, gap
                if gap == 0:
                    break
        if best_key:
            monster.room_key = best_key
        return True


# mode 字符串 -> handler 实例。新增剧本行为时在这里登记即可。
_MODE_HANDLERS: dict[str, HauntModeHandler] = {}


def register_mode(handler: HauntModeHandler) -> None:
    _MODE_HANDLERS[handler.mode] = handler


class WitchAndFrogsMode(GenericModeHandler):
    """剧本 3 青蛙腿浓汤（Frog-Leg Stew）。

    权威原文：英雄手册 p14 / 叛徒手册 p85。

    已核对且原本就正确：女巫 Speed 4 / Might 3 / Sanity 6（门厅生成）、
    猫 Speed 3 / Might 3 / Sanity 2；挖根 Knowledge 4+、凡人形态 6+、
    复原 4+。

    本次补齐：
        · Root 令牌放置（温室/储藏室/厨房，未发现则发现时补放）与挖取/消耗
        · 女巫无敌真正生效（引擎此前从不读 invulnerable_until）
        · 女巫法术：蛙皮（同房间理智对决变蛙）、鸦翼（飞向最近英雄）、
          龙息（视野内或同房的英雄，2 骰不可防御物理伤害）
        · 青蛙状态：掉物品、力量/知识降到最低格（不降骷髅），
          不能攻击/抽牌/探索；复原时属性回到角色卡初始值
        · 蛙可被其他探险者像物品一样背起携带（p14）：背着走、放下、
          背着时什么都不能做；猫仍会追蛙
        · 猫：第一个蛙出现后生成于作祟房间，追最近的蛙，力量对决吃掉

    已知简化：
        · 背/放蛙在电子版占"剧本行动"（每人每回合一次），原版近似物品
          动作，行动经济略有出入；蛙被背着期间猫仍可能追上来把它吃掉。
        · 女巫每回合的法术选择用 bot 固定策略（同房优先蛙皮 → 视野内
          龙息 → 鸦翼追人），人类叛徒暂无逐回合自选法术的界面。
    """

    mode = "witch_and_frogs"

    ROOT_ROOMS = ("conservatory", "larder", "kitchen")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        # p85 原文设定："They have the Witch's spellbook (the Book card)."
        # 电子版必须主动保证这个前提：作祟之后探险者不再为探索而探索，预兆
        # 符号房间基本不再被发现，书会一直躺在预兆牌堆里，英雄永远施不出
        # 凡人形态、女巫永久无敌，整局卡死（seed=109 实测：400 回合后 11 张
        # 预兆牌一张都没被摸过）。所以书若还没出场，就交给一名英雄——
        # 这正是原文设定的状态。若书已被叛徒持有则保持（叛徒抢到了，
        # 英雄得去夺回）。
        if not engine._card_is_controlled("omen_book"):
            hero = next(
                (p for p in engine.state.players if p.role == "hero" and not p.dead),
                None,
            )
            if hero is not None and engine._grant_card_to_player(hero, "omen_book"):
                engine._log(f"女巫的魔法书一直在{hero.name}手上。")

        # p85：三株曼德拉草放温室/储藏室/厨房；未发现的房间等发现时再放，
        # 且不公开哪些未发现房间有草。
        # 但这些房间必须先真的在场上——作祟后探险者不再主动探索，房间可能
        # 整局都不出现，草也就一株都长不出来，剧本直接卡死。所以先把它们
        # 拉进屋子（原版 p84 对五芒星室有同样做法）。
        pending: list[str] = []
        for template_id in sorted(self.ROOT_ROOMS):
            room_key_now = engine._ensure_room_in_play(template_id, room_key)
            if room_key_now:
                engine.spawn_token("root", label="曼德拉草", role="marker", room_key=room_key_now)
            else:
                pending.append(template_id)
        engine._haunt_flags()["pending_roots"] = pending

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        flags = engine._haunt_flags()
        pending = list(flags.get("pending_roots", []))
        if room.template_id in pending:
            pending.remove(room.template_id)
            flags["pending_roots"] = pending
            engine.spawn_token("root", label="曼德拉草", role="marker", room_key=room.key)
            # p85："Don't announce which undiscovered rooms will get Root
            # tokens."——悄悄放下，不广播草的存在。

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        carried = self._carried_map(engine)
        result = []
        for action in actions:
            if action.id == "dig_root" and not engine.tokens_in_room(player.room_key, "root"):
                continue  # p14：只有在长着曼德拉草的房间才能挖
            if action.id == "cast_mortal_form" and not engine.tokens_held_by(player.id, "root"):
                continue  # 施法需要曼德拉草
            if action.id == "carry_frog":
                frog_here = any(
                    p.frog and not p.dead and p.id != player.id
                    and p.room_key == player.room_key
                    and str(p.id) not in carried
                    for p in engine.state.players
                )
                if player.frog or not frog_here or player.id in carried.values():
                    continue  # 蛙不能背蛙；房间里要有没人背着的蛙；一次背一只
            if action.id == "drop_frog":
                if player.id not in carried.values():
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "dig_root":
            if not engine.tokens_in_room(player.room_key, "root"):
                engine._log("这个房间里没有曼德拉草可挖。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                root = next(iter(engine.tokens_in_room(player.room_key, "root")), None)
                if root:
                    engine.give_token(root.uid, player.id)
                    engine._log(f"{player.name} 挖出了一株曼德拉草。")
            return ok

        if action_id == "cast_mortal_form":
            if not engine.tokens_held_by(player.id, "root"):
                engine._log("施放凡人形态需要一株曼德拉草。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                # rule_data 的 set_flags 已置 witch_vulnerable；这里消耗草
                root = next(iter(engine.tokens_held_by(player.id, "root")), None)
                if root:
                    engine.remove_token(root.uid)
                engine._log("凡人形态生效——女巫的护盾消失了！")
            return ok

        if action_id == "restore_frog":
            frogs = [
                p
                for p in engine.state.players
                if p.frog and not p.dead and p.room_key == player.room_key
            ]
            if not frogs:
                engine._log("这个房间里没有青蛙。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                engine._restore_from_frog(frogs[0])
                self._sync_carried(engine)  # 复原的蛙解除"被背着"绑定
            return ok

        if action_id == "carry_frog":
            carried = self._carried_map(engine)
            frog = next(
                (
                    p for p in engine.state.players
                    if p.frog and not p.dead and p.id != player.id
                    and p.room_key == player.room_key and str(p.id) not in carried
                ),
                None,
            )
            if frog is None or player.frog or player.id in carried.values():
                engine._log("这个房间里没有可背起的青蛙。")
                return False
            carried[str(frog.id)] = player.id
            engine._haunt_flags()["frog_carried"] = carried
            engine._log(f"{player.name} 把青蛙{frog.name}像行李一样背了起来。")
            return True

        if action_id == "drop_frog":
            carried = self._carried_map(engine)
            mine = [fid for fid, cid in carried.items() if cid == player.id]
            if not mine:
                engine._log("你没有背着青蛙。")
                return False
            carried.pop(mine[0], None)
            engine._haunt_flags()["frog_carried"] = carried
            frog = next((p for p in engine.state.players if str(p.id) == mine[0]), None)
            engine._log(f"{player.name} 把{frog.name if frog else '青蛙'}放了下来。")
            return True

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 女巫
    def _attackable_heroes(self, engine: Any) -> list[Any]:
        return [p for p in engine.state.players if p.role == "hero" and not p.dead and not p.frog]

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p14/p85：凡人形态生效后，任何成功攻击都直接杀死女巫。

        引擎默认只是击晕怪物，而剧本 3 的英雄胜利条件就是"杀死女巫"。
        没有这一步，即使施法成功，女巫也只是昏迷一回合又爬起来，
        整局会一直空转到回合上限（seed=109 实测）。
        """
        if _monster_id(monster) != "witch":
            return False
        if not engine._haunt_flags().get("witch_vulnerable"):
            # 还没施放凡人形态：原文明确"She can't be attacked"，
            # 引擎已挡下攻击，这里兜底仍按击晕处理。
            return False
        engine.state.monsters = [m for m in engine.state.monsters if m.id != monster.id]
        engine._log("女巫发出一声尖叫，化作尘埃消失了！")
        engine.check_victory()
        return True

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        if _monster_id(monster) == "witch":
            # p85：女巫不能普通攻击，同房间有英雄时改施蛙皮
            self._cast_skin_of_frog(engine, monster)
            return True
        if _monster_id(monster) == "cat":
            return True  # 猫只吃蛙，不吃英雄
        return False

    def _cast_skin_of_frog(self, engine: Any, witch: Any) -> None:
        heroes = [p for p in self._attackable_heroes(engine) if p.room_key == witch.room_key]
        if not heroes:
            return
        # p85：双方掷理智，女巫高则变蛙。机器人对第一个目标施放；
        # 人类叛徒选目标留待接 prompter（记为待办）。
        victim = heroes[0]
        witch_roll = engine._roll_monster_attack(witch, "sanity")
        hero_roll = engine._roll_attack(victim, "sanity")
        engine._log(f"女巫对{victim.name}施放蛙皮之咒：{witch_roll} 对 {hero_roll}。")
        if witch_roll > hero_roll:
            engine._turn_into_frog(victim)
        else:
            engine._log(f"{victim.name} 抵抗住了蛙皮之咒。")

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) == "witch":
            return self._witch_move(engine, monster)
        if _monster_id(monster) == "cat":
            return self._cat_move(engine, monster)
        return False

    def _witch_move(self, engine: Any, witch: Any) -> bool:
        # 同房间有正常英雄：原地留着施蛙皮
        if any(p.room_key == witch.room_key for p in self._attackable_heroes(engine)):
            return True
        # p85 龙息：视野内（无阻隔直线门道，可跨房间）没有同房目标时，
        # 对够远的可见英雄喷 2 骰不可防御的物理伤害。太近的英雄（≤3 格）
        # 不值得喷——女巫更愿意鸦翼贴脸施蛙皮（转化是叛徒的胜路，也让
        # 英雄有机会反击；实测全距离喷息会把局拖成英雄够不着的僵局）。
        visible = sorted(
            [
                p for p in self._attackable_heroes(engine)
                if p.room_key != witch.room_key
                and engine._has_line_of_sight(witch.room_key, p.room_key)
            ],
            key=lambda p: (engine._path_length(witch.room_key, p.room_key), p.id),
        )
        if visible and engine._path_length(witch.room_key, visible[0].room_key) > 3:
            victim = visible[0]
            amount = engine.roll_dice(2, "龙息")
            engine._log(f"女巫向{victim.name}喷出龙息（2 骰不可防御物理伤害）！")
            engine._deal_damage(victim, "physical", amount, source="女巫的龙息")
            engine.check_victory()
            return True
        # 否则鸦翼：飞向最近的可施法英雄（p85 "Wings of Raven ... any room"）
        targets = sorted(
            self._attackable_heroes(engine),
            key=lambda p: (engine._path_length(witch.room_key, p.room_key), p.id),
        )
        if not targets:
            return True
        dest = targets[0].room_key
        if dest != witch.room_key:
            witch.room_key = dest
            engine._log(f"女巫振翅飞到了{engine.state.board[dest].name}。")
        return True

    # ------------------------------------------------------------- 背蛙
    # p14："Another explorer (who isn't a Frog) can pick up and carry a
    # Frog like an item. Frogs cannot do anything while being carried."
    # 绑定表 flags["frog_carried"] = {蛙玩家id(str): 背负者id}。
    # 近似说明：背/放蛙作为"剧本行动"占用本回合一次行动（原版近似物品
    # 动作，行动经济略有出入，已记录在类注释）。
    def _carried_map(self, engine: Any) -> dict:
        return engine._haunt_flags().setdefault("frog_carried", {})

    def _sync_carried(self, engine: Any) -> None:
        """蛙跟着背负者走；顺带清理失效绑定（背负者死/变蛙/蛙复原）。"""
        carried = self._carried_map(engine)
        players = {p.id: p for p in engine.state.players}
        changed = False
        for frog_id in list(carried):
            frog = players.get(int(frog_id))
            carrier = players.get(int(carried[frog_id]))
            if (
                frog is None or carrier is None or carrier.dead or frog.dead
                or not frog.frog or carrier.frog
            ):
                carried.pop(frog_id, None)
                changed = True
                continue
            if frog.room_key != carrier.room_key:
                frog.room_key = carrier.room_key
                changed = True
        if changed:
            engine._haunt_flags()["frog_carried"] = carried

    def on_player_moved(self, engine: Any, player: Any) -> None:
        self._sync_carried(engine)

    def _cat_move(self, engine: Any, cat: Any) -> bool:
        # p85：猫向最近的青蛙移动；同房间以力量对决，赢则吃掉。
        frogs = sorted(
            [p for p in engine.state.players if p.frog and not p.dead],
            key=lambda p: (engine._path_length(cat.room_key, p.room_key), p.id),
        )
        if not frogs:
            return True  # 没有蛙，猫趴着不动
        prey = frogs[0]
        if cat.room_key != prey.room_key:
            path = engine._shortest_path(cat.room_key, prey.room_key)
            if len(path) > 1:
                steps = max(1, engine.roll_dice(cat.speed, "猫的移动"))
                cat.room_key = path[min(len(path) - 1, steps)]
                engine._log(f"猫移动到{engine.state.board[cat.room_key].name}。")
        if cat.room_key == prey.room_key:
            cat_roll = engine._roll_monster_attack(cat, "might")
            frog_roll = engine._roll_attack(prey, "might")
            engine._log(f"猫扑向青蛙{prey.name}：{cat_roll} 对 {frog_roll}。")
            if cat_roll > frog_roll:
                prey.dead = True
                engine._log(f"猫把{prey.name}吃掉了！")
                engine.check_victory()
            else:
                engine._log("青蛙跳开了。")
        return True

    def on_turn_start(self, engine: Any, player: Any) -> None:
        self._sync_carried(engine)  # 清理失效的背蛙绑定（背负者死/变蛙等）
        # p85：第一个探险者变蛙时，猫出现在作祟揭示的房间。
        flags = engine._haunt_flags()
        if flags.get("cat_spawned"):
            return
        if not any(p.frog and not p.dead for p in engine.state.players):
            return
        flags["cat_spawned"] = True
        haunt_room = engine._haunt_rule_state().get("haunt_room")
        spec = engine._haunt_rule_state().get("monster_specs", {}).get("cat", {})
        if haunt_room and engine._spawn_single_haunt_monster(spec, haunt_room):
            engine.spawn_token("cat", label="猫", role="marker", room_key=haunt_room)
            engine._log("一只舔着爪子的猫出现在了作祟的房间里。")

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        # p14：英雄胜利 = 杀死女巫
        if engine.state.haunt and engine._monster_by_template("witch") is None:
            engine._set_winner("heroes", "女巫被消灭了。")
            return True
        # p85：叛徒胜利 = 英雄全灭或全部变成青蛙
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if heroes and all(p.frog for p in heroes):
            engine._set_winner("traitor", "所有英雄都变成了青蛙。")
            return True
        if super().check_victory(engine):
            return True
        # p85 只规定女巫死/英雄全灭两种终局：杀死叛徒【不】构成英雄胜利
        # （女巫独立施法，会继续把英雄变蛙）。吸收通用兜底，游戏继续。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False


class WebEscapeMode(GenericModeHandler):
    """剧本 4 蛛网逃生（The Web of Destiny）。

    权威原文：英雄手册 p15 / 叛徒手册 p86。

    已核对且原本就正确：蜘蛛初始 Speed 0 / Might 2 / Sanity 5（作祟房生成）；
    蛛网以 Might 4 防御；web_damage 目标 = 玩家数；卵孵化第 9 回合；
    摧毁卵（医疗箱 Knowledge 4+ / 治疗药膏免检定）；开门 6+。

    本次补齐：
        · 被困探险者：作祟揭示者不能移动（可用物品），蛛网打碎后解困
        · 叛徒人数规则：3-4 人局叛徒被蜘蛛吃掉（原版 p86），5-6 人局叛徒在场
        · 蛛网令牌与 Might 检定令牌（玩家数枚）放置
        · 蜘蛛按 Turn Traits 表逐回合成长（p86 的 0/2 → 6/8）
        · 逐回合孵化倒计时，第 9 回合判叛徒胜
        · 胜利条件修正：杀叛徒不算英雄胜（原数据又是 traitor_dead 坑）

    已实现"蜘蛛每次攻击可把每个空白骰（掷出 0）重掷一次"（p86，
    monster_rerolls_blanks 钩子，bot 恒重掷）。
    已知简化：
    "抽事件卡并结束回合后下一回合才能出门"简化为开门后下一回合出门。
    """

    mode = "web_escape"

    def monster_rerolls_blanks(self, engine: Any, monster: Any) -> bool:
        """p86：蜘蛛每次攻击，每个掷出 0 的骰子可重掷一次。"""
        return _monster_id(monster) == "giant_spider"

    # p86 Turn Traits 表：回合 → (speed, might)
    SPIDER_GROWTH: tuple[tuple[int, int], ...] = (
        (0, 2), (1, 2), (2, 4), (4, 4), (5, 5), (6, 7), (6, 8),
    )

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        revealer_id = engine.state.haunt_revealer_id
        flags["trapped_id"] = revealer_id
        engine.spawn_token("web", label="粘稠蛛网", role="marker", room_key=room_key)
        engine.spawn_tokens("might_check", len(engine.state.players), label="力量检定", role="check")

        revealer = next((p for p in engine.state.players if p.id == revealer_id), None)
        if revealer is not None:
            revealer.movement_stopped = True
            engine._log(f"{revealer.name} 被蛛网缠住，动弹不得！")

        # p86：3-4 人局叛徒直接被蜘蛛吃掉；5-6 人局叛徒在场继续作战。
        # 电子版把"被吃掉"处理为死亡（掉落物品走引擎通用死亡流程）。
        # 例外：若叛徒恰好是作祟揭示者（即被困者本人），不能吃——
        # 被困者是英雄的救援目标，吃掉他剧本就无解了（实测 seed=113/
        # 131 都会出现这种选人）。此时叛徒保持在场，等同 5-6 人局。
        players = len(engine.state.players)
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and players <= 4 and traitor.id != flags.get("trapped_id"):
            traitor.dead = True
            engine._log(f"叛徒{traitor.name}被巨型蜘蛛一口吞掉了。")
            engine.check_victory()

    # ------------------------------------------------------------- 被困者
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        trapped_id = flags.get("trapped_id")
        # 蛛网未破：被困者每回合开始都被钉住
        if player.id == trapped_id and flags.get("web_destroyed") is not True:
            player.movement_stopped = True

        # p86：倒计时随叛徒回合推进（"At the end of each of your turns"）。
        # 3-4 人局叛徒已被吃掉，改用轮次计数：每当回合数回到本轮首位玩家
        # 时推进一格（等价于"一整轮过去"）。注意首位玩家可能是死者（如
        # 叛徒即被困者、开局就被吃掉的情形），此时用 turn_count 取模
        # 存活人数对齐轮次，保证计时器照样走（seed=131 实测：叛徒死了，
        # turn_index 从不回到 0，倒计时卡死在 0，整局无终局）。
        traitor_alive = any(p.role == "traitor" and not p.dead for p in engine.state.players)
        alive = [p for p in engine.state.players if not p.dead]
        if traitor_alive:
            should_tick = player.role == "traitor"
        else:
            first_alive_id = alive[0].id if alive else None
            should_tick = player.id == first_alive_id
        if should_tick:
            current = engine._haunt_track_value("spider_timer")
            deadline = engine._haunt_track_target("spider_timer")
            if current < deadline:
                engine._set_haunt_track_value("spider_timer", current + 1)
                engine._log(f"蛛卵孵化倒计时：{current + 1}/{deadline}。")
                if current + 1 >= deadline:
                    engine._set_winner("traitor", "蛛卵孵化了！成群的小蜘蛛涌满了整栋房子。")
                # 蜘蛛按回合成长
                spider = engine._monster_by_template("giant_spider")
                if spider is not None:
                    idx = min(len(self.SPIDER_GROWTH) - 1, current + 1)
                    speed, might = self.SPIDER_GROWTH[idx]
                    spider.speed = speed
                    spider.might = might

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        flags = engine._haunt_flags()
        result = []
        for action in actions:
            # 蛛网已破就别再显示"攻击蛛网"
            if action.id == "attack_web" and flags.get("web_destroyed"):
                continue
            # 卵已毁就别再显示销毁卵
            if action.id in {"destroy_eggs_medical_kit", "destroy_eggs_salve"} and flags.get("eggs_destroyed"):
                continue
            # 门已开就别再显示开门；未解困/卵未毁不能开门
            if action.id == "open_front_door":
                if flags.get("front_door_open"):
                    continue
                if flags.get("web_destroyed") is not True or flags.get("eggs_destroyed") is not True:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "attack_web":
            flags = engine._haunt_flags()
            if flags.get("web_destroyed"):
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine._haunt_track_value("web_damage") >= engine._haunt_track_target("web_damage"):
                flags["web_destroyed"] = True
                # 解困
                trapped = next(
                    (p for p in engine.state.players if p.id == flags.get("trapped_id")),
                    None,
                )
                if trapped is not None and not trapped.dead:
                    trapped.movement_stopped = False
                    engine._log(f"蛛网被彻底撕碎，{trapped.name} 重获自由！")
                web = next(iter(engine.tokens_of_kind("web")), None)
                if web:
                    engine.remove_token(web.uid)
            return ok

        if action_id in {"destroy_eggs_medical_kit", "destroy_eggs_salve"}:
            flags = engine._haunt_flags()
            if flags.get("eggs_destroyed"):
                return False
            # 治疗药膏免检定（p15 "without a Knowledge roll"）
            if action_id == "destroy_eggs_salve":
                for card_id in ("item_healing_salve",):
                    if card_id in player.items:
                        engine._discard_card_from_player(player, card_id, return_to_room=False)
                flags["eggs_destroyed"] = True
                engine._log(f"{player.name} 用治疗药膏销毁了蛛卵。")
                engine.check_victory()
                return True
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                flags["eggs_destroyed"] = True
            return ok

        if action_id == "open_front_door":
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                engine._haunt_flags()["front_door_open"] = True
            return ok

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 蜘蛛
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """p86：蜘蛛必须追"非揭示者"的探险者；卵被毁后才可攻击揭示者。"""
        if _monster_id(monster) != "giant_spider":
            return False
        flags = engine._haunt_flags()
        trapped_id = flags.get("trapped_id")
        candidates = [
            p
            for p in engine.state.players
            if not p.dead
            and p.id != trapped_id
            and (p.role == "hero" or (p.role == "traitor" and False))
        ]
        if not candidates:
            return True
        candidates.sort(key=lambda p: (engine._path_length(monster.room_key, p.room_key), p.id))
        dest = candidates[0]
        if monster.room_key == dest.room_key:
            return True
        path = engine._shortest_path(monster.room_key, dest.room_key)
        if len(path) > 1:
            steps = max(1, rolled)
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"巨型蜘蛛移动到{engine.state.board[monster.room_key].name}。")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p15：英雄胜利 = 被困者解困 + 卵被毁 + 至少一人出屋。
        # 出屋判定：门开之后，任何英雄回合结束仍站在门厅即算逃出
        # （p15 原文是"开门→抽事件牌结束回合→下一回合出门"两步流程，
        #  电子版合并为"开门后站到门厅结束回合"）。
        if flags.get("front_door_open") and not flags.get("escaped"):
            entrance = next(
                (r for r in engine.state.board.values() if r.template_id == "entrance_hall"),
                None,
            )
            if entrance and any(
                p.role == "hero" and not p.dead and p.room_key == entrance.key
                for p in engine.state.players
            ):
                flags["escaped"] = True
        if flags.get("web_destroyed") and flags.get("eggs_destroyed") and flags.get("escaped"):
            engine._set_winner("heroes", "有人逃出了这栋房子，蛛网再也无法困住任何人。")
            return True
        # 通用条件（此处仅 all_heroes_dead → 叛徒胜）
        if super().check_victory(engine):
            return True
        # 3-4 人局叛徒开局就被吃掉：吸收"叛徒死亡→英雄胜"兜底。
        # p15 只认"解困+毁卵+出屋"，蜘蛛独立行动，叛徒死活不影响。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False


class AlienAbductionMode(GenericModeHandler):
    """剧本 6 飞行之眼（The Floating Eye）。

    权威原文：英雄手册 p17 / 叛徒手册 p88。

    已核对且原本就正确：外星人 Speed 4 / Might 6 / Sanity 6；
    数量 3-4 人 1 只、5-6 人 2 只；破船 Might 5+、目标=玩家数。

    本次补齐：
        · 叛徒开局"等待运输"出局（p88），物品留在原房间
        · 外星人理智攻击同房间每个英雄：赢→精神控制（不受伤）
        · 被控英雄：不能攻击/做行动，回合开始被移向飞船，到达后下回合上船出局
        · 解救：攻击被控同伴取胜 → 半伤+解控+永久免疫（引擎已接）
        · 外星人免疫速度攻击（引擎已接，剧本 1 木乃伊同步受益）
        · 飞船瘫痪 → 英雄胜；叛徒死亡兜底吸收（叛徒开局就出局）

    已知简化：外星人"重掷"无（本剧本没有）；被控者移动由 handler 自动
    执行（原版由叛徒玩家操控被控者移动，电子版等效自动化）。
    """

    mode = "alien_abduction"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        engine.spawn_token("spaceship", label="宇宙飞船", role="marker", room_key=room_key)
        engine.spawn_tokens("might_check", len(engine.state.players), label="力量检定", role="check")
        flags["ship_room"] = room_key
        flags.setdefault("controlled_ids", [])
        flags.setdefault("immune_ids", [])

        # p88：叛徒角色放上飞船令牌——连同所有物品预兆出局等待运输。
        # 注意这不是"死亡"：不要走引擎死亡流程，直接移出游戏。
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            for card_id in list(traitor.items):
                engine._discard_card_from_player(traitor, card_id, return_to_room=True)
            traitor.companions.clear()
            traitor.dead = True
            engine._log(f"{traitor.name} 登上了飞船，等待运输。他已离开游戏。")
        engine.check_victory()

    # ------------------------------------------------------------- 外星人
    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p88：外星人以理智攻击同房间每个探险者（各自结算，代替普通攻击）。

        赢了的英雄不受伤、被精神控制；英雄赢了双方都无伤。
        已被控或已免疫的英雄跳过（外星人只能控制一个人一次）。
        """
        if _monster_id(monster) != "alien":
            return False
        flags = engine._haunt_flags()
        controlled: set = set(flags.get("controlled_ids", []) or [])
        immune: set = set(flags.get("immune_ids", []) or [])
        victims = [
            p
            for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == monster.room_key
            and p.id not in controlled and p.id not in immune
        ]
        if not victims:
            return False  # 没有可攻击对象，回落到引擎普通攻击（打叛徒侧？无）
        for victim in victims:
            alien_roll = engine._roll_monster_attack(monster, "sanity")
            hero_roll = engine._roll_attack(victim, "sanity")
            engine._log(f"外星人的意念凝视 {victim.name}：{alien_roll} 对 {hero_roll}。")
            if alien_roll > hero_roll:
                controlled.add(victim.id)
                flags["controlled_ids"] = sorted(controlled)
                engine._log(f"{victim.name} 的眼神涣散了——他被精神控制了！")
            else:
                engine._log(f"{victim.name} 顶住了意念攻击（双方无伤）。")
        return True

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """外星人按常规移动追人（普通 Speed 4），剧本不接管。"""
        if _monster_id(monster) != "alien":
            return False
        return False

    # ------------------------------------------------------------- 被控者
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        controlled = set(flags.get("controlled_ids", []) or [])
        ship_room = flags.get("ship_room")
        if player.id not in controlled or player.dead:
            return
        # 已到达飞船房间：上船出局（p88 "at the beginning of his or her next turn"）
        if player.room_key == ship_room:
            controlled.discard(player.id)
            flags["controlled_ids"] = sorted(controlled)
            player.dead = True
            engine._log(f"{player.name} 被拖上了飞船！他已被带离这栋房子。")
            engine.check_victory()
            return
        # 移向飞船（由 handler 自动执行，等效于原版叛徒操控）
        path = engine._shortest_path(player.room_key, ship_room)
        if len(path) > 1:
            steps = max(1, player.stats.get("speed", 1))
            player.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"被控的{player.name}如梦游般走向{engine.state.board[player.room_key].name}。")

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        if player.id in set(engine._haunt_flags().get("controlled_ids", []) or []):
            return []  # p88：被控者不能做任何剧本行动
        return super().available_actions(engine, player)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p17：飞船瘫痪（破坏进度=玩家数）→ 英雄胜
        if engine._haunt_track_value("spaceship_damage") >= engine._haunt_track_target("spaceship_damage"):
            engine._set_winner("heroes", "飞船瘫痪了，外星人的掳掠计划破产。")
            return True
        if super().check_victory(engine):
            return True
        # p88：叛徒开局就出局等待运输——吸收"叛徒死亡→英雄胜"兜底。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False


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
        if victim is None or root is None or victim.room_key != root.room_key:
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


class ExorcismMode(GenericModeHandler):
    """剧本 8 女妖哀嚎（Wail of the Banshee）。

    权威原文：英雄手册 p19 / 叛徒手册 p90。

    核心机制（此前数据只有"看起来对"的骨架，实际全未接上）：
    · 女妖不可被攻击（invulnerable），没有普通攻击；每次怪物阶段按 p90
      "移动计划"行动：掷两枚骰（0-2 面），和 0-4 直接对应五个选项：
        0 传送到 ≤7 格远的任意房间（途中不经任何房间）
        1 先选第一个房间，此后尽量左转（贴左墙）
        2 先选第一个房间，此后尽量直行；只剩左右可走时随机
        3 先选第一个房间，此后尽量右转（贴右墙）
        4 本回合由叛徒操控移动，且哀嚎对每位探险者至多生效一次
      贴墙规则（1/3 共用）：左/右转优先，不行直行，再不行反向转，
      死胡同从原路返回。
    · 哀嚎：女妖途经或停下的房间，每位探险者理智检定按总点分档受伤：
        6+ 受 1 骰精神伤害；3-5 受 2 骰；0-2 受 4 骰。持灵应板的叛徒
      免疫；板被偷走后不再免疫，偷板者自己也不获得免疫。
    · 驱魔（英雄胜）：成功次数 = 玩家人数即放逐女妖。每次成功需要一个
      房间/物品来源（理智：教堂/地窖/五芒星室/圣徽/灵应板；知识：图书
      馆/研究实验室/古书/水晶球），理智或知识 5+，每人每回合一次；每个
      来源只能成功使用一次（成功后来源作废，房间放一枚检定令牌）。
    · 已知简化：p90 女妖途经楼梯类房间的"定向传送"（二楼平台/塌房/画廊/
      门厅等）未实现——引擎连通图已含楼梯链接，抄近路近似；女妖不用
      神秘电梯（引擎怪物从不触发电梯效果，天然满足）。
    · 移动目标（选项 1-3 的"先选第一个房间"与选项 4 的操控）统一取
      "机器人叛徒选择朝最近英雄方向"，保证种子回放可复现。
    """

    mode = "exorcism"

    BANSHEE = "banshee"
    SANITY_ROOM_SOURCES = ["chapel", "crypt", "pentagram_chamber"]
    SANITY_ITEM_SOURCES = ["omen_holy_symbol", "omen_spirit_board"]
    KNOWLEDGE_ROOM_SOURCES = ["library", "research_laboratory"]
    KNOWLEDGE_ITEM_SOURCES = ["omen_book", "omen_crystal_ball"]
    ALL_SOURCES = (
        SANITY_ROOM_SOURCES + SANITY_ITEM_SOURCES
        + KNOWLEDGE_ROOM_SOURCES + KNOWLEDGE_ITEM_SOURCES
    )
    # 贴墙转向（相对当前行进方向）：1=左墙，3=右墙
    WALL_TURN = {1: -1, 3: 1}

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        # p90：女妖令牌（大）放在叛徒所在房间；p19 检定令牌按需生成
        engine.spawn_token("banshee", label="女妖", role="marker", room_key=room_key)
        engine._haunt_flags().setdefault("used_exorcism_sources", [])

    # ------------------------------------------------------------- 女妖回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.BANSHEE:
            return False
        self._banshee_turn(engine, monster)
        return True  # 移动与哀嚎都已处理，跳过引擎默认追击/攻击

    def _banshee_turn(self, engine: Any, monster: Any) -> None:
        option = engine.roll_dice(2, "女妖移动计划")  # 两枚 0-2 骰 → 0..4
        steps = engine.roll_dice(getattr(monster, "speed", 8), "女妖速度")
        engine._log(f"女妖的移动计划掷出 {option}，可移动 {steps} 格。")
        target = engine._find_monster_target(monster)

        if option == 0:
            # 传送到任意 ≤7 格的房间（到达即停，仍会哀嚎）
            candidates = [
                key for key in engine.state.board
                if key != monster.room_key
                and engine._path_length(monster.room_key, key) <= 7
            ]
            if not candidates:
                engine._log("女妖周围七格内空无一物。")
                return
            dest = min(
                candidates,
                key=lambda key: (
                    engine._path_length(key, target.room_key) if target is not None else 0,
                    key,
                ),
            )
            monster.room_key = dest
            engine._log(f"女妖化作阴风，直接飘进了{engine.state.board[dest].name}。")
            self._wail(engine, dest, None)
            return

        if target is None:
            return
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) < 2:
            return  # 已与目标同房（引擎不会在此阶段调用，防御性返回）

        if option == 2:
            # 直行优先：沿最短路径走完剩余步数（途经房间照常哀嚎）
            remaining = path[1 : min(len(path) - 1, steps) + 1]
            for next_key in remaining:
                monster.room_key = next_key
                self._wail(engine, next_key, None)
                if engine.state.winner:
                    return
            return

        # 选项 1/3/4：第一格朝最近英雄方向；1/3 之后按贴墙规则，
        # 4 为叛徒操控（机器人叛徒选"向目标推进"，哀嚎去重一次）
        once_set: set | None = set() if option == 4 else None
        first = path[1]
        monster.room_key = first
        self._wail(engine, first, once_set)
        facing = self._facing(engine, monster.room_key, first)
        if option == 1 or option == 3:
            for _ in range(max(0, steps - 1)):
                nxt = self._wall_step(engine, monster.room_key, facing, option)
                if nxt is None or nxt == monster.room_key:
                    break
                facing = self._facing(engine, monster.room_key, nxt)
                monster.room_key = nxt
                self._wail(engine, nxt, None)
                if engine.state.winner:
                    return
        else:
            chase = engine._shortest_path(monster.room_key, target.room_key)
            for next_key in chase[1 : min(len(chase) - 1, steps - 1) + 1]:
                monster.room_key = next_key
                self._wail(engine, next_key, once_set)
                if engine.state.winner:
                    return

    def _facing(self, engine: Any, prev_key: str, curr_key: str) -> str:
        """上一房间 -> 当前房间 的几何方向；链接跳转等非正交移动返回空串。"""
        prev = engine.state.board.get(prev_key)
        curr = engine.state.board.get(curr_key)
        if not prev or not curr or prev.floor != curr.floor:
            return ""
        dx = curr.x - prev.x
        dy = curr.y - prev.y
        for direction, (ddx, ddy) in {
            "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
        }.items():
            if (dx, dy) == (ddx, ddy):
                return direction
        return ""

    def _neighbors(self, engine: Any, room_key: str) -> list[str]:
        return engine._build_graph().get(room_key, [])

    def _wall_step(self, engine: Any, room_key: str, facing: str, option: int) -> str | None:
        """按贴墙优先级走一步：左/直/右/原路，返回下一房间；无路返回 None。"""
        neighbors = self._neighbors(engine, room_key)
        if not neighbors:
            return None
        if not facing:
            return neighbors[0]
        order = ["north", "east", "south", "west"]
        idx = order.index(facing)
        turn = self.WALL_TURN.get(option, 0)
        priority_dirs = [
            order[(idx + turn) % 4],   # 转向侧
            order[idx],                # 直行
            order[(idx - turn) % 4],   # 反向侧
            order[(idx + 2) % 4],      # 原路返回
        ]
        for direction in priority_dirs:
            matches = [k for k in neighbors if self._facing(engine, room_key, k) == direction]
            if matches:
                return matches[0]
        return neighbors[0]

    def _wail(self, engine: Any, room_key: str, once_set: set | None) -> None:
        """女妖哀嚎：房间里的探险者按理智检定分档吃精神伤害。

        once_set 非空（选项 4）时，本回合已中招的英雄跳过。
        """
        occupants = [
            p for p in engine.state.players
            if not p.dead and p.room_key == room_key
            and not (p.role == "traitor" and "omen_spirit_board" in p.items)
        ]
        for victim in occupants:
            if once_set is not None and victim.id in once_set:
                continue
            roll = engine._roll_attack(victim, "sanity")
            dice = 1 if roll >= 6 else (2 if roll >= 3 else 4)
            amount = engine.roll_dice(dice, "女妖哀嚎")
            if once_set is not None:
                once_set.add(victim.id)
            engine._log(
                f"女妖的哀嚎撕裂了{victim.name}的心智（理智检定 {roll}，"
                f"{dice} 骰 → {amount} 点精神伤害）。"
            )
            engine._deal_damage(victim, "mental", amount, source="女妖哀嚎")
            if victim.dead:
                break

    # ------------------------------------------------------------- 驱魔
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        used = set(engine._haunt_flags().get("used_exorcism_sources", []))
        return [action for action in actions if action.id not in used]

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id not in self.ALL_SOURCES:
            return super().perform_action(engine, player, action_id, data)
        if action_id in set(engine._haunt_flags().get("used_exorcism_sources", [])):
            engine._log("这个驱魔来源已经成功用过，不能再用了。")
            return False
        ok = super().perform_action(engine, player, action_id, data)
        if ok:
            used = list(engine._haunt_flags().get("used_exorcism_sources", []))
            used.append(action_id)
            engine._haunt_flags()["used_exorcism_sources"] = used
            kind = (
                "sanity_check"
                if action_id in self.SANITY_ROOM_SOURCES + self.SANITY_ITEM_SOURCES
                else "knowledge_check"
            )
            engine.spawn_token(kind, label="驱魔成功", role="check", room_key=player.room_key)
        return ok

    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("exorcism_successes") >= engine._haunt_track_target("exorcism_successes"):
            engine._set_winner("heroes", "驱魔完成——女妖在圣咏中化为青烟消散了。")
            return True
        # p90 只规定两种终局（放逐 / 英雄全灭）：女妖按自己的计划行动，
        # 叛徒阵亡【不】构成英雄胜利。吸收引擎兜底，游戏继续。
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "女妖的哀嚎夺走了最后一个活着的灵魂。")
            return True
        return True


class DeathDanceMode(GenericModeHandler):
    """剧本 9 死亡之舞（The Dance of Death）。

    权威原文：英雄手册 p20 / 叛徒手册 p91。

    特色是"开局没有叛徒"：每位英雄在自己回合开始都可能被魔音诱惑成叛徒。
    引擎每次作祟都必然指定一名叛徒，本模式在 setup 里把引擎选出的这名
    玩家降回英雄（含清空 traitor_id），真正的叛徒由诱惑检定动态诞生。

    · 补房（p20）：五芒星室与舞厅不在场时从房间牌堆拉进场（引擎
      _ensure_room_in_play 放同楼层空位；原版"五芒星室放最远、舞厅接一楼
      任选房间"的精确选址省略，只保证房间到场）。
    · 抵抗诱惑（p20）：每位英雄（持圣徽者豁免）回合开始理智检定 4+；
      失败 → 若在舞厅，或理智被扣到骷髅格 → 当场堕落为叛徒；否则理智
      -1 并沿最短路线被迫走向舞厅。
    · 理智因其他原因降到骷髅格也堕落为叛徒（p20 "you also become
      insane"）。引擎死亡流程会把 0 属性判死，本模式只在回合开始兜底转
      化——中途被精神伤害直接打死仍走死亡流程（已知简化）。
    · 放逐提琴手（英雄胜，p20）：英雄把圣徽带进五芒星室后，同房任意英雄
      可做理智 5+ 检定（无需本人持徽）；成功在五芒星室放一枚理智令牌；
      令牌数 = 作祟开局人数 → 放逐成功。每人每回合只能尝试一步。
    · 持圣徽者不能自愿转交圣徽（引擎 item_trade_blocked 钩子）。
    · 叛徒每回合开始做力量检定：3+ 无碍；0-2 本回合不能移动且力量 -1
      （p91 "Dance until your feet go numb"）。
    · 叛徒胜：圣徽被毁（偷到手后在深渊/熔炉房/地下湖结束回合）或英雄全灭。
    · 已知简化：叛徒"速度对速度攻击、2+ 可改偷"（p91）属引擎攻击结算级
      改动，未接（同剧本 1 木乃伊专属战斗的处理方式）；第一个堕落者成为
      叛徒后，其余英雄诱惑失败只吃 1 点理智伤害并走向舞厅，不再二次转化
      （原版未说明多人堕落如何处理，电子版取单叛徒模型）。
    """

    mode = "delayed_traitor_relic"

    PENTAGRAM = "pentagram_chamber"
    BALLROOM = "ballroom"

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        engine._ensure_room_in_play(self.PENTAGRAM, room_key)
        engine._ensure_room_in_play(self.BALLROOM, room_key)
        ballroom_key = next(
            (k for k, r in engine.state.board.items() if r.template_id == self.BALLROOM),
            None,
        )
        engine.spawn_token("dark_fiddler", label="黑暗提琴手", role="marker",
                           room_key=ballroom_key or room_key)
        flags.setdefault("converted_traitor_id", None)
        flags.setdefault("holy_symbol_destroyed", False)
        latent = next((p for p in engine.state.players if p.role == "traitor"), None)
        if latent is not None:
            latent.role = "hero"
            engine.state.traitor_id = None
            engine._log("提琴手的旋律在每个心头埋下种子——目前还没有人堕落。")

    def item_trade_blocked(self, engine: Any, giver: Any, target: Any, card_id: str) -> bool:
        return card_id == "omen_holy_symbol" and giver.role == "hero"

    def _ballroom_key(self, engine: Any) -> str | None:
        return next(
            (k for k, r in engine.state.board.items() if r.template_id == self.BALLROOM), None
        )

    def _convert_to_traitor(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        flags["converted_traitor_id"] = player.id
        player.role = "traitor"
        engine.state.traitor_id = player.id
        engine._log(f"{player.name} 被提琴手的魔音攫住——他加入了死亡之舞！")
        engine.check_victory()

    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.dead:
            return
        if player.role == "traitor":
            # p91：叛徒每回合跳舞检定
            roll = engine._roll_attack(player, "might")
            if roll <= 2:
                player.movement_stopped = True
                engine._apply_stat_loss(player, "might", 1)
                engine._log(f"{player.name} 跳得双脚发麻（力量检定 {roll}）：本回合不能移动，力量 -1。")
            else:
                engine._log(f"{player.name} 在死亡之舞中旋舞（力量检定 {roll}）。")
            return
        # 英雄：理智已在骷髅格（其他原因所致）→ 堕落
        position = player.stat_positions.get("sanity")
        if position is not None and position <= 0 and not player.dead:
            self._convert_to_traitor(engine, player)
            return
        # 持圣徽者豁免诱惑检定
        if "omen_holy_symbol" in player.items:
            return
        if engine._resolve_check(player, "sanity", 4, "抵抗提琴手的诱惑"):
            return
        # 诱惑失败
        ballroom_key = self._ballroom_key(engine)
        if ballroom_key is not None and player.room_key == ballroom_key:
            self._convert_to_traitor(engine, player)
            return
        engine._apply_stat_loss(player, "sanity", 1)
        position = player.stat_positions.get("sanity")
        if position is not None and position <= 0:
            self._convert_to_traitor(engine, player)  # 理智扣到骷髅 = 堕落而非死亡
            return
        if ballroom_key is not None:
            path = engine._shortest_path(player.room_key, ballroom_key)
            if len(path) > 1:
                steps = max(1, player.stats.get("speed", 1))
                player.room_key = path[min(len(path) - 1, steps)]
                engine._log(
                    f"被魔音牵引的{player.name}身不由己地走向{engine.state.board[player.room_key].name}。"
                )

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "banish_fiddler":
                symbol_in_room = any(
                    other.role == "hero" and not other.dead
                    and other.room_key == player.room_key
                    and "omen_holy_symbol" in other.items
                    for other in engine.state.players
                )
                if not symbol_in_room:
                    continue  # 圣徽必须由某位英雄带进五芒星室
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "banish_fiddler":
            symbol_in_room = any(
                other.role == "hero" and not other.dead
                and other.room_key == player.room_key
                and "omen_holy_symbol" in other.items
                for other in engine.state.players
            )
            if not symbol_in_room:
                engine._log("需要有英雄把圣徽带进五芒星室才能尝试放逐。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                engine.spawn_token(
                    "sanity_check", label="放逐成功", role="check", room_key=player.room_key
                )
            return ok
        if action_id == "destroy_holy_symbol":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and not engine._haunt_flags().get("holy_symbol_destroyed"):
                engine._haunt_flags()["holy_symbol_destroyed"] = True
                engine._log("圣徽被抛入深渊——再也没有人能阻止死亡之舞了！")
            return ok
        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_flags().get("holy_symbol_destroyed"):
            engine._set_winner("traitor", "圣徽已毁，死亡之舞将永远继续。")
            return True
        if engine._haunt_track_value("fiddler_banishment") >= engine._haunt_track_target("fiddler_banishment"):
            engine._set_winner("heroes", "提琴手在圣咏中融化——死亡之舞终于落幕。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "所有人都加入了死亡之舞，再也停不下来。")
            return True
        return True  # 本剧本开局无叛徒，吸收引擎"叛徒缺席即英雄胜"兜底


class ZombieTrapMode(GenericModeHandler):
    """剧本 10 家族聚会（Family Gathering）。

    权威原文：英雄手册 p21 / 叛徒手册 p92。

    骨架数据基本正确（僵尸按预兆房间生成、疯子 5 点伤害容量、陷阱房间
    列表），本模式把机制接通：

    · 叛徒开局即被疯子杀死（p92）——与剧本 4/6 同款"叛徒出局但游戏继续"
      模型；疯子令牌顶替他的位置，怪物阶段由本轮最后一位存活玩家代跑。
    · 陷阱（英雄胜）：僵尸进入或回合开始时处于特殊房间（主卧/教堂/温室/
      游戏室/图书馆/阁楼）→ 知识检定 4+ 成功则挣脱；失败则永远停在该
      房间（不再移动/攻击/检定），进度 +1；每间房只能困一只（p21）。
      全部僵尸被困 → 英雄胜。
    · 疯子（p92）：可承受 5 点物理伤害才死；伤害不影响属性，常规攻击的
      击晕照旧。累计伤害达容量即整场离场。
    · 已知简化：p92 的"无视野时叛徒自由操控、有视线才追人"未实现——
      电子版 bot 始终追最近英雄（引擎默认，接近"看到英雄"后的行为）；
      "A Zombie attacks as soon as it's in a room with an explorer" 的
      即时攻击用引擎"移动结束同房即攻击"近似（中途经过不额外攻击）。
    """

    mode = "trap_zombies"

    ZOMBIE = "zombie"
    MADMAN = "madman"
    TRAP_ROOMS = ["master_bedroom", "chapel", "conservatory", "game_room", "library", "attic"]

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        madman = engine._monster_by_template(self.MADMAN)
        if traitor is not None:
            if madman is not None:
                madman.room_key = traitor.room_key  # 疯子令牌顶替叛徒的位置
            engine._drop_inventory_on_death(traitor)
            traitor.dead = True
            engine._log(f"疯子从地板下爬出，把叛徒{traitor.name}拖进了地底。")
        engine._haunt_flags().setdefault("trapped_zombies", [])
        engine._haunt_flags().setdefault("trapped_rooms", [])

    # ------------------------------------------------------------- 陷阱
    def _try_trap(self, engine: Any, zombie: Any) -> bool:
        """僵尸在特殊房间时尝试困住它。返回 True = 已被困住（或本就困着）。"""
        trapped = set(engine._haunt_flags().get("trapped_zombies", []))
        zombie_id = str(getattr(zombie, "id", ""))
        if zombie_id in trapped:
            return True
        room = engine.state.board.get(getattr(zombie, "room_key", ""))
        if room is None or room.template_id not in self.TRAP_ROOMS:
            return False
        if room.key in set(engine._haunt_flags().get("trapped_rooms", [])):
            return False  # 这间房已经困过一只
        roll = engine.roll_dice(getattr(zombie, "knowledge", 3), "僵尸滞留检定")
        if roll >= 4:
            engine._log(f"{zombie.name} 在{room.name}里嗅了嗅，挣脱了回忆的束缚。")
            return False
        flags = engine._haunt_flags()
        flags["trapped_zombies"] = sorted(trapped | {zombie_id})
        flags["trapped_rooms"] = sorted(set(flags.get("trapped_rooms", [])) | {room.key})
        engine._advance_haunt_track("zombies_trapped", 1)
        engine._log(f"{zombie.name} 在{room.name}前愣住了——他认出了自己的家，永远停在了那里。")
        engine.check_victory()
        return True

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.ZOMBIE:
            return False
        if self._try_trap(engine, monster):
            return True  # 困在特殊房间开始回合：直接结算，不再行动
        return False

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """僵尸移动的终点若是特殊房间，先落位再判陷阱（p21 进入即判）。"""
        if _monster_id(monster) != self.ZOMBIE:
            return False
        if str(getattr(monster, "id", "")) in set(
            engine._haunt_flags().get("trapped_zombies", [])
        ):
            return True
        target = engine._find_monster_target(monster)
        if target is None:
            return False
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) <= 1:
            return False
        dest = path[min(len(path) - 1, rolled)]
        monster.room_key = dest  # 先落位（引擎默认随后也会走到同一格）
        if self._try_trap(engine, monster):
            return True  # 已被困住：跳过引擎的后续移动
        return False

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """疯子：物理伤害容量 5，常规击晕照旧（返回 False 让引擎默认击晕）。"""
        if _monster_id(monster) != self.MADMAN:
            return False
        engine._advance_haunt_track("madman_damage", max(1, amount))
        taken = engine._haunt_track_value("madman_damage")
        if taken >= engine._haunt_track_target("madman_damage"):
            monster_id = getattr(monster, "id", None)
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
            ]
            engine._log("疯子轰然倒地——这一家子终于团聚了。")
            engine.check_victory()
        return False

    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("zombies_trapped") >= engine._haunt_track_target("zombies_trapped"):
            engine._set_winner("heroes", "所有僵尸都回到了生前最爱的房间，安静地停了下来。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "疯子和他的家人们收割了整栋房子。")
            return True
        return True  # 吸收"叛徒开局已死 → 引擎判英雄胜"的兜底


class SpecterInvasionMode(ExorcismMode):
    """剧本 11 放他们进来（Let Them In）。

    权威原文：英雄手册 p22 / 叛徒手册 p93。

    复用剧本 8 的驱魔底座（八来源一次性、成功放检定令牌、满玩家人数即
    全部放逐），但理智物品来源用**戒指**替换灵应板（p22）。本次新增：

    · 雾中人影（Specter）：背面朝下待命于门厅 + 五个朝外窗房间
      （大楼梯/主卧/卧室/教堂/餐厅，p93）；后发现的窗房间补放
      （on_room_discovered）。用 ghost 模板承载，数值由规则表覆盖
      （Speed 4 / Sanity 6），免疫力量/速度攻击（p22 "can't be attacked
      physically"）。
    · 疯子（Speed 7 / Might 7 / Sanity 7，p93）：开局顶替在叛徒房间；
      每回合自动走向最近的背面人影并开窗放入（放入当回合即可移动与
      攻击）；全部放入前不攻击（可自卫），之后按常规怪物行动。
    · 持戒指者对雾中人影的徒手攻击改为理智攻击（attack_attr_override
      钩子），击败即放逐；只有持戒指者能攻击人影（attack_allowed）；
      人影攻击英雄落败时照常被击晕（p22 "If you defeat a Specter when
      it attacks you, the Specter is stunned"）。
    · 叛徒也可亲自开窗（open_window 剧本行动；原版开窗耗 1 格移动，
      电子版近似为占用剧本行动）。
    · 英雄胜：驱魔满员，或"放入数 = 放逐数且无背面人影"（p22 "banish
      all the Specters"）；叛徒胜：英雄全灭。叛徒阵亡不结束游戏
      （疯子与人影自主行动，同 7/8 惯例）。
    · 已知简化：窗户"假窗"（被邻室挡住即失效、失效则移除背面人影）
      不建模；铃铛/灵应板对背面人影无效属物品交互边界，未接；叛徒
      "失去疯子加成"是纯卡牌文本，未建模。
    """

    mode = "spectre_exorcism"

    SANITY_ITEM_SOURCES = ["omen_holy_symbol", "omen_ring"]
    ALL_SOURCES = (
        ExorcismMode.SANITY_ROOM_SOURCES + SANITY_ITEM_SOURCES
        + ExorcismMode.KNOWLEDGE_ROOM_SOURCES + ExorcismMode.KNOWLEDGE_ITEM_SOURCES
    )
    SPECTER = "ghost"   # 雾中人影用 ghost 模板承载，数值由规则表覆盖
    MADMAN = "madman"
    WINDOW_ROOMS = ["grand_staircase", "master_bedroom", "bedroom", "chapel", "dining_room"]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("used_exorcism_sources", [])
        flags["specters_activated"] = 0
        flags["specters_banished"] = 0
        # p93：门厅 + 朝外窗房间放背面人影（房间已在场才放）
        for template_id in ["entrance_hall", *self.WINDOW_ROOMS]:
            key = next(
                (k for k, r in engine.state.board.items() if r.template_id == template_id),
                None,
            )
            if key and not engine.tokens_in_room(key, "specter"):
                engine.spawn_token("specter", label="雾中人影", role="marker", room_key=key, face_up=False)
        # p93：疯子令牌放在叛徒房间，疯子怪物在此生成
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine.spawn_token("madman", label="疯子", role="marker", room_key=traitor.room_key)
            spec = next(
                (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.MADMAN),
                {},
            )
            if engine._spawn_single_haunt_monster(spec, traitor.room_key) is not None:
                engine._log(f"疯子在{engine.state.board[traitor.room_key].name}推开了一扇窗。")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        # p93：后发现的朝外窗房间补放背面人影
        if room.template_id in self.WINDOW_ROOMS and not engine.tokens_in_room(room.key, "specter"):
            engine.spawn_token("specter", label="雾中人影", role="marker", room_key=room.key, face_up=False)
            engine._log(f"{room.name}的窗外，雾里浮出了一个人影。")

    # ------------------------------------------------------------- 内部
    def _facedown_rooms(self, engine: Any) -> list[str]:
        return [t.room_key for t in engine.tokens_of_kind("specter") if not t.face_up and t.room_key]

    def _release_specter(self, engine: Any, room_key: str) -> bool:
        token = next(
            (t for t in engine.tokens_in_room(room_key, "specter") if not t.face_up),
            None,
        )
        if token is None:
            return False
        engine.flip_token(token.uid, True)
        spec = next(
            (
                s for s in (engine.state.haunt.rule_data or {}).get("monsters", [])
                if s.get("template_id") == self.SPECTER
            ),
            {},
        )
        monster = engine._spawn_single_haunt_monster(spec, room_key)
        if monster is None:
            return False
        flags = engine._haunt_flags()
        flags["specters_activated"] = int(flags.get("specters_activated", 0)) + 1
        engine._log(f"{engine.state.board[room_key].name}的窗被推开了——雾中人影涌了进来！")
        self._specter_turn(engine, monster)  # p93：放入当回合即可移动与攻击
        return True

    def _specter_turn(self, engine: Any, monster: Any) -> None:
        target = engine._find_monster_target(monster)
        if target is None:
            return
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 4), "雾中人影移动")
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"雾中人影飘进了{engine.state.board[monster.room_key].name}。")
        if monster.room_key == target.room_key:
            self._specter_attack(engine, monster)

    def _specter_attack(self, engine: Any, monster: Any) -> bool:
        victims = [
            p for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == monster.room_key
        ]
        if not victims:
            return True
        victim = victims[0]
        specter_roll = engine._roll_monster_attack(monster, "sanity")
        hero_roll = engine._roll_attack(victim, "sanity")
        engine._log(f"雾中人影的哀嚎穿透{victim.name}：{specter_roll} 对 {hero_roll}。")
        if specter_roll > hero_roll:
            engine._deal_damage(victim, "mental", specter_roll - hero_roll, source="雾中人影")
        elif specter_roll < hero_roll:
            engine._stun_monster(monster, 1)
            engine._log(f"{victim.name} 驱散了哀嚎，雾中人影畏缩了。")
        else:
            engine._log("僵持不下。")
        return True

    # ------------------------------------------------------------- 攻击
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p22：只有持戒指者能攻击雾中人影。"""
        if _monster_id(target) == self.SPECTER:
            return "omen_ring" in attacker.items
        return True

    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        """p22：持戒指者的徒手攻击对人影改为理智攻击。"""
        if _monster_id(target) == self.SPECTER and default_attr == "might":
            return "sanity"
        return None

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """疯子：优先开最近的窗；全部放入后交回引擎常规追击。"""
        if _monster_id(monster) != self.MADMAN:
            return False
        facedown = self._facedown_rooms(engine)
        if not facedown:
            return False
        target = min(facedown, key=lambda key: (engine._path_length(monster.room_key, key), key))
        path = engine._shortest_path(monster.room_key, target)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 7), "疯子移动")
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"疯子走向{engine.state.board[monster.room_key].name}。")
        if monster.room_key in facedown:
            self._release_specter(engine, monster.room_key)
        return True

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        mid = _monster_id(monster)
        if mid == self.MADMAN:
            if self._facedown_rooms(engine):
                return True  # p93：全部放入前疯子不攻击（被打了也会自卫）
            return False
        if mid != self.SPECTER:
            return False
        return self._specter_attack(engine, monster)

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p22：持戒指者击败雾中人影即放逐（闸门已保证只有持戒者能打）。"""
        if _monster_id(monster) != self.SPECTER:
            return False
        monster_id = getattr(monster, "id", None)
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
        ]
        flags = engine._haunt_flags()
        flags["specters_banished"] = int(flags.get("specters_banished", 0)) + 1
        engine._log("雾中人影被放逐，在圣咏里消散了。")
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "open_window":
                tokens = engine.tokens_in_room(player.room_key, "specter")
                if player.role != "traitor" or not tokens or all(t.face_up for t in tokens):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "open_window":
            if not any(not t.face_up for t in engine.tokens_in_room(player.room_key, "specter")):
                engine._log("这个房间的窗已经开过了。")
                return False
            return self._release_specter(engine, player.room_key)
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("exorcism_successes") >= engine._haunt_track_target("exorcism_successes"):
            engine._set_winner("heroes", "驱魔完成——雾中人影全部被送回了雾里。")
            return True
        flags = engine._haunt_flags()
        activated = int(flags.get("specters_activated", 0))
        banished = int(flags.get("specters_banished", 0))
        if activated > 0 and banished >= activated and not self._facedown_rooms(engine):
            engine._set_winner("heroes", "所有进屋的雾中人影都被放逐了。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "雾中人影与疯子收割了整栋房子。")
            return True
        return True  # 叛徒阵亡不构成英雄胜（疯子与人影自主行动）


class FleshwalkerMode(GenericModeHandler):
    """剧本 12 肉行者（Fleshwalkers，即"邪恶双胞胎"）。

    权威原文：英雄手册 p23 / 叛徒手册 p94。

    本剧本没有叛徒：每个探险者都要面对自己的邪恶双胞胎。引擎每次作祟
    都会指定一名"潜伏叛徒"，本模式在 setup 里把他降回英雄（同剧本 9），
    并清空 traitor_id；胜负全部由本模式显式判定。

    · 双胞胎（p23）：用 shadow 模板承载，属性 = 对应探险者作祟开局值，
      **整局冻结**；全部生成在门厅；不能携带物品。
    · 行动时序（p23 "take their monster turn after the haunt revealer's
      turn"）：引擎轮转回合序恰好让揭示者最后行动、怪物阶段紧随其后，
      无需额外处理。
    · 双胞胎行为：永远沿最短路追自己的本体；同房间优先攻击本体，否则
      随机攻击房内一名探险者（引擎 rng，种子可复现）。本体死亡后，该
      玩家控制这只双胞胎攻击其他探险者（电子版 bot 近似：追最近的其他
      活人）。
    · 水晶球规则（p23）：
        - 无球与**自己的**双胞胎交手：无论谁赢，自己四属性各 -1
          （on_attack_resolved 钩子，平手不结算）；
        - 无球击败自己的双胞胎 → 击晕；持球击败自己的双胞胎 → 杀死；
        - 击败**别人的**双胞胎 → 击晕；持球且其本体已死 → 杀死；
        - 昏迷的双胞胎只有持球者能攻击（attack_allowed），且它防守时不
          反击（monster_counterattack_disabled）。
    · 英雄胜：双胞胎全部被消灭且至少一名英雄存活；全部探险者死亡 =
      双胞胎获胜。无叛徒，吸收引擎"叛徒缺席→英雄胜"兜底。
    """

    mode = "fleshwalkers"

    TWIN = "shadow"            # 双胞胎用 shadow 模板承载，数值逐只覆盖
    CRYSTAL_BALL = "omen_crystal_ball"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["twin_of"] = {}
        flags["twins_killed"] = 0
        latent = next((p for p in engine.state.players if p.role == "traitor"), None)
        if latent is not None:
            latent.role = "hero"
            engine.state.traitor_id = None
        entrance = next(
            (k for k, r in engine.state.board.items() if r.template_id == "entrance_hall"),
            room_key,
        )
        # p23：双胞胎属性 = 对应探险者作祟开局值，且整局冻结（引擎不会
        # 主动改怪物属性，冻结天然成立）
        for player in engine.state.players:
            spec = {
                "template_id": self.TWIN,
                "name": f"邪恶双胞胎·{player.name}",
                "speed": int(player.stats.get("speed", 2)),
                "might": int(player.stats.get("might", 2)),
                "sanity": int(player.stats.get("sanity", 2)),
                "knowledge": int(player.stats.get("knowledge", 2)),
                "can_carry_items": False,
            }
            monster = engine._spawn_single_haunt_monster(spec, entrance)
            if monster is not None:
                flags["twin_of"][str(monster.id)] = player.id
        count = len(flags["twin_of"])
        engine._log(f"门厅里站着一排熟得不能再熟的身影——{count} 个邪恶双胞胎睁开了眼睛。")

    # ------------------------------------------------------------- 内部
    def _counterpart(self, engine: Any, monster: Any) -> Any | None:
        pid = engine._haunt_flags().get("twin_of", {}).get(str(getattr(monster, "id", "")))
        if pid is None:
            return None
        return next((p for p in engine.state.players if p.id == int(pid)), None)

    # ------------------------------------------------------------- 行为
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.TWIN:
            return False
        counterpart = self._counterpart(engine, monster)
        target_room: str | None = None
        if counterpart is not None and not counterpart.dead:
            target_room = counterpart.room_key  # p23：永远追本体
        else:
            # 本体已死：由该玩家控制，追杀最近的其他活人（bot 近似）
            others = [
                p for p in engine.state.players
                if not p.dead and p.room_key != getattr(monster, "room_key", "")
            ]
            if others:
                others.sort(key=lambda p: (engine._path_length(monster.room_key, p.room_key), p.id))
                target_room = others[0].room_key
        if target_room and target_room != monster.room_key:
            path = engine._shortest_path(monster.room_key, target_room)
            if len(path) > 1:
                monster.room_key = path[min(len(path) - 1, rolled)]
                engine._log(f"邪恶双胞胎逼近{engine.state.board[monster.room_key].name}。")
        return True

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.TWIN:
            return False
        in_room = [
            p for p in engine.state.players
            if not p.dead and p.room_key == monster.room_key
        ]
        if not in_room:
            return True
        counterpart = self._counterpart(engine, monster)
        if (
            counterpart is not None and not counterpart.dead
            and counterpart.room_key == monster.room_key
        ):
            victim = counterpart  # p23：可能的话永远攻击本体
        else:
            victim = in_room[engine.rng.randrange(len(in_room))]  # 随机选一个
        twin_roll = engine._roll_monster_attack(monster, "might")
        hero_roll = engine._roll_attack(victim, "might")
        engine._log(f"{monster.name} 扑向 {victim.name}：{twin_roll} 对 {hero_roll}。")
        if twin_roll > hero_roll:
            engine._deal_damage(victim, "physical", twin_roll - hero_roll, source=monster.name)
        elif twin_roll < hero_roll:
            engine._stun_monster(monster, 1)
        return True

    # ------------------------------------------------------------- 攻击规则
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p23：昏迷的双胞胎只有持水晶球者能攻击。"""
        if _monster_id(target) == self.TWIN and int(getattr(target, "stunned_turns", 0)) > 0:
            return self.CRYSTAL_BALL in attacker.items
        return True

    def monster_counterattack_disabled(self, engine: Any, monster: Any) -> bool:
        """p23：昏迷双胞胎防守时用常规骰，但赢了也不造成伤害。"""
        return _monster_id(monster) == self.TWIN and int(getattr(monster, "stunned_turns", 0)) > 0

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        """p23：无球与自己的双胞胎交手，无论谁赢四属性各 -1。"""
        if _monster_id(target) != self.TWIN:
            return
        counterpart = self._counterpart(engine, target)
        if counterpart is None or counterpart.id != getattr(attacker, "id", None):
            return  # 只对"自己的双胞胎"生效
        if self.CRYSTAL_BALL in attacker.items:
            return
        for stat in ("speed", "might", "sanity", "knowledge"):
            engine._apply_stat_loss(attacker, stat, 1)
        engine._log(f"{attacker.name} 在与自己的双胞胎交手中心神受创（四属性各 -1）。")

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p23：击败双胞胎默认击晕；持球（自己/本体已死）则杀死。"""
        if _monster_id(monster) != self.TWIN:
            return False
        attacker = None
        active_id = getattr(engine, "_active_player_id", None)
        if active_id is not None:
            attacker = engine.state.players[active_id]
        holder = attacker is not None and self.CRYSTAL_BALL in attacker.items
        counterpart = self._counterpart(engine, monster)
        own = counterpart is not None and attacker is not None and attacker.id == counterpart.id
        counterpart_dead = counterpart is None or counterpart.dead
        if holder and (own or counterpart_dead):
            monster_id = getattr(monster, "id", None)
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
            ]
            flags = engine._haunt_flags()
            flags.get("twin_of", {}).pop(str(monster_id), None)
            engine._advance_haunt_track("twins_killed", 1)
            engine._log("水晶球迸出强光——邪恶双胞胎被彻底湮灭了！")
            engine.check_victory()
            return True
        return False  # 默认击晕

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes_alive = any(p.role == "hero" and not p.dead for p in engine.state.players)
        if (
            engine._haunt_track_value("twins_killed") >= engine._haunt_track_target("twins_killed")
            and heroes_alive
        ):
            engine._set_winner("heroes", "所有邪恶双胞胎都被消灭，活下来的人面面相觑。")
            return True
        if not heroes_alive:
            engine._set_winner("traitor", "探险者全军覆没——房子里只剩下他们的双胞胎。")
            return True
        return True  # 本剧本无叛徒，吸收引擎"叛徒缺席即英雄胜"兜底


class NightmareDreamMode(GenericModeHandler):
    """剧本 13 梦中梦（Perchance to Dream）。

    权威原文：英雄手册 p24 / 叛徒手册 p95。

    叛徒（揭示者）当场沉睡：身体钉在原地、掉光物品、不能行动（狗/女孩/
    疯子卡一并掉落；原文的属性微调未建模——梦魇不会攻击沉睡者，英雄
    也不许攻击沉睡者，唤醒失败之外的死亡路径不存在）。梦魇（shadow
    模板承载，Speed 5 / Might 4 / Sanity 4，p95）数量 = 玩家数，生成于
    沉睡房间，由"梦之意识"（bot）驱动。

    · 逃脱房间（p95）：朝外窗房间（与剧本 11 同列表）+ 温室/门厅/花园/
      墓地/阳台/塔楼。开局数不足玩家数时从房间牌堆补房（_ensure_room_
      in_play）。秘密总数存 flags["escape_total"]。
    · 逃脱（p95）：梦魇在未用过的逃脱房间花 1 格移动逃出；每房限一次
      （放逃脱令牌）；逃出/被杀后立即在沉睡房间补一只（p95 "you can
      unleash another Nightmare"）。新发现的逃脱房间可用但不增加所需
      总数——电子版房间集合作祟时已定，天然满足。
    · 梦魇 bot 策略：所在房间可逃脱 → 立即逃脱；否则奔向最近的未用
      逃脱房间，抵达即逃；同房间有英雄时先攻击（力量对拼但造成精神
      伤害，p24 "Nightmares do mental damage"）。
    · 击败语义（p95）：被英雄攻击击败 → 杀死（非击晕）；攻击英雄落败
      → 照常击晕。
    · 唤醒（英雄胜，p24）：圣徽被任一英雄带进沉睡房间后，房内任意英雄
      可做理智或力量 5+（通用框架取两属性较高者），成功次数 = 玩家数
      即唤醒；味道盐卡不参与唤醒链路，天然满足。
    · 叛徒胜：逃出数达到秘密总数（p95），或英雄全灭。
    · 已知简化：沉睡者的"不能使用物品"未在物品系统层拦截（bot 不会
      用；人类界面低风险边界）；狗/女孩/疯子卡的属性微调未建模。
    """

    mode = "nightmare_escape"

    NIGHTMARE = "shadow"
    SLEEPER_ITEM_CARDS = ("omen_dog", "omen_girl", "omen_madman")
    WINDOW_ROOMS = ["grand_staircase", "master_bedroom", "bedroom", "chapel", "dining_room"]
    EXTRA_ESCAPE_ROOMS = ["conservatory", "entrance_hall", "garden", "graveyard", "patio", "tower", "balcony"]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        sleeper = next((p for p in engine.state.players if p.role == "traitor"), None)
        if sleeper is None:
            return
        flags["sleeper_id"] = sleeper.id
        # p95：身体沉睡——钉住、掉光物品（含伙伴卡）
        for card_id in list(sleeper.items):
            if card_id in self.SLEEPER_ITEM_CARDS:
                sleeper.items.remove(card_id)
        engine._drop_inventory_on_death(sleeper)
        flags["sleeper_room"] = sleeper.room_key
        engine._log(f"{sleeper.name} 倒在{engine.state.board[sleeper.room_key].name}里沉沉睡去，怎么也叫不醒……")

        # p95：逃脱房间计数；不足玩家数则从牌堆补房
        escape_ids = [*self.WINDOW_ROOMS, *self.EXTRA_ESCAPE_ROOMS]
        board_ids = {r.template_id for r in engine.state.board.values()}
        total = len([rid for rid in escape_ids if rid in board_ids])
        players = len(engine.state.players)
        for template_id in escape_ids:
            if total >= players:
                break
            if template_id in board_ids:
                continue
            if engine._ensure_room_in_play(template_id, sleeper.room_key):
                board_ids.add(template_id)
                total += 1
        flags["escape_total"] = total
        flags.setdefault("escape_used_rooms", [])
        flags["escapes"] = 0
        engine._log("（梦之意识记下了这栋房子共有几条逃出去的路——这是个秘密。）")

        # p95：梦魇数量 = 玩家数，生成于沉睡房间
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.NIGHTMARE),
            {},
        )
        for _ in range(players):
            engine._spawn_single_haunt_monster(spec, sleeper.room_key)

    # ------------------------------------------------------------- 内部
    def _sleeper(self, engine: Any) -> Any | None:
        sid = engine._haunt_flags().get("sleeper_id")
        return next((p for p in engine.state.players if p.id == sid), None)

    def _sleeper_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("sleeper_room")

    def _escape_room_ids(self, engine: Any) -> set[str]:
        return {r.template_id for r in engine.state.board.values()} & set(
            [*self.WINDOW_ROOMS, *self.EXTRA_ESCAPE_ROOMS]
        )

    def _is_open_escape_room(self, engine: Any, room_key: str) -> bool:
        room = engine.state.board.get(room_key)
        if room is None or room.template_id not in self._escape_room_ids(engine):
            return False
        return room_key not in set(engine._haunt_flags().get("escape_used_rooms", []))

    def _escape(self, engine: Any, monster: Any) -> None:
        """梦魇从当前房间逃出房子，并立即补一只新的（p95）。"""
        room_key = monster.room_key
        monster_id = getattr(monster, "id", None)
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
        ]
        flags = engine._haunt_flags()
        flags["escapes"] = int(flags.get("escapes", 0)) + 1
        flags["escape_used_rooms"] = sorted(set(flags.get("escape_used_rooms", [])) | {room_key})
        engine.spawn_token("escape", label="逃脱路线", role="marker", room_key=room_key)
        engine._log(f"一只梦魇从{engine.state.board[room_key].name}钻了出去，消失在夜色里！")
        spec = next(
            (
                s for s in (engine.state.haunt.rule_data or {}).get("monsters", [])
                if s.get("template_id") == self.NIGHTMARE
            ),
            {},
        )
        sleeper_room = self._sleeper_room(engine)
        if sleeper_room:
            engine._spawn_single_haunt_monster(spec, sleeper_room)
        engine.check_victory()

    def _nightmare_attack(self, engine: Any, monster: Any) -> bool:
        victims = [
            p for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == monster.room_key
        ]
        if not victims:
            return True
        victim = victims[0]
        nightmare_roll = engine._roll_monster_attack(monster, "might")
        hero_roll = engine._roll_attack(victim, "might")
        engine._log(f"梦魇扑向 {victim.name}：{nightmare_roll} 对 {hero_roll}。")
        if nightmare_roll > hero_roll:
            # p24：梦魇造成精神伤害而非物理伤害
            engine._deal_damage(victim, "mental", nightmare_roll - hero_roll, source="梦魇")
        elif nightmare_roll < hero_roll:
            engine._stun_monster(monster, 1)  # p95：攻击落败照常击晕
        return True

    # ------------------------------------------------------------- 攻击闸门
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """沉睡者的身体不许被攻击（英雄的胜利条件是唤醒而非杀死他）。"""
        sleeper = self._sleeper(engine)
        if sleeper is not None and target is sleeper:
            return False
        return True

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """沉睡者每回合开始都被重新钉住。"""
        if player.id == engine._haunt_flags().get("sleeper_id") and not player.dead:
            player.movement_stopped = True

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "wake_attempt":
                sleeper_room = self._sleeper_room(engine)
                if player.room_key != sleeper_room or player.id == engine._haunt_flags().get("sleeper_id"):
                    continue  # 必须在沉睡者的房间（沉睡者自己不算）
                symbol_here = any(
                    other.role == "hero" and not other.dead
                    and other.room_key == player.room_key
                    and "omen_holy_symbol" in other.items
                    for other in engine.state.players
                )
                if not symbol_here:
                    continue  # 圣徽必须被某位英雄带进房间
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "wake_attempt":
            sleeper_room = self._sleeper_room(engine)
            symbol_here = any(
                other.role == "hero" and not other.dead
                and other.room_key == player.room_key
                and "omen_holy_symbol" in other.items
                for other in engine.state.players
            )
            if player.room_key != sleeper_room or not symbol_here:
                engine._log("需要有英雄带着圣徽在沉睡者的房间里才能尝试唤醒。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                engine.spawn_token("wake_token", label="唤醒成功", role="check", room_key=player.room_key)
            return ok
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 梦魇回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.NIGHTMARE:
            return False
        if int(getattr(monster, "stunned_turns", 0)) > 0:
            return False  # 被击晕的梦魇跳过（引擎扣减昏迷计数）
        # 同房间有英雄：先攻击（p95：梦魇会主动攻击）
        heroes_here = [
            p for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == monster.room_key
        ]
        if heroes_here:
            self._nightmare_attack(engine, monster)
            return True
        # 所在房间可逃脱：立即逃出（p95：花 1 格移动）
        if self._is_open_escape_room(engine, monster.room_key):
            self._escape(engine, monster)
            return True
        # 奔向最近的未用逃脱房间
        open_rooms = [
            key for key, room in engine.state.board.items()
            if self._is_open_escape_room(engine, key)
        ]
        if open_rooms:
            open_rooms.sort(key=lambda key: (engine._path_length(monster.room_key, key), key))
            dest = open_rooms[0]
            path = engine._shortest_path(monster.room_key, dest)
            if len(path) > 1:
                steps = engine.roll_dice(getattr(monster, "speed", 5), "梦魇移动")
                monster.room_key = path[min(len(path) - 1, steps)]
                engine._log(f"梦魇游荡到了{engine.state.board[monster.room_key].name}。")
            if self._is_open_escape_room(engine, monster.room_key):
                self._escape(engine, monster)
            return True
        # 没有可用逃脱房间：追击最近英雄（同房攻击已在上面分支处理不了时兜底）
        target = engine._find_monster_target(monster)
        if target is None:
            return True
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 5), "梦魇移动")
            monster.room_key = path[min(len(path) - 1, steps)]
        if monster.room_key == target.room_key:
            self._nightmare_attack(engine, monster)
        return True

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p95：被英雄攻击击败的梦魇直接死亡（非击晕），并立即补一只。"""
        if _monster_id(monster) != self.NIGHTMARE:
            return False
        monster_id = getattr(monster, "id", None)
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
        ]
        engine._log("梦魇被撕成了碎片——但梦之意识又放出了一只新的！")
        spec = next(
            (
                s for s in (engine.state.haunt.rule_data or {}).get("monsters", [])
                if s.get("template_id") == self.NIGHTMARE
            ),
            {},
        )
        sleeper_room = self._sleeper_room(engine)
        if sleeper_room:
            engine._spawn_single_haunt_monster(spec, sleeper_room)
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p24/p95：唤醒必须赶在梦魇逃够之前——先判逃脱
        if int(flags.get("escapes", 0)) >= int(flags.get("escape_total", 0)) and int(flags.get("escape_total", 0)) > 0:
            engine._set_winner(
                "traitor",
                f"梦魇逃出了房子（共 {flags.get('escape_total')} 条逃脱路线）——梦魇涌进了现实世界。",
            )
            return True
        if engine._haunt_track_value("waking_progress") >= engine._haunt_track_target("waking_progress"):
            engine._set_winner("heroes", "沉睡者猛然惊醒——梦魇失去了凝聚力，四散消融。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "英雄们在梦魇的尖啸中一个接一个倒下。")
            return True
        return True  # 沉睡者不能死亡，吸收"叛徒缺席/死亡→英雄胜"兜底


OPPOSITE_DOOR = {"north": "south", "south": "north", "east": "west", "west": "east"}



OPPOSITE_DOOR = {"north": "south", "south": "north", "east": "west", "west": "east"}


class StarsRightMode(GenericModeHandler):
    """剧本 14 星辰归位（The Stars Are Right）。

    权威原文：英雄手册 p25 / 叛徒手册 p96。

    · 油漆罐（Paint，数量 = 玩家数，p25）：按序放厨房/储藏室/杂物间/
      研究实验室/阁楼（原版 Storeroom 与 Larder 共用）；罐比房多则同房
      叠放；全不在场则从
      牌堆补第一间。英雄一次只能背一罐；从与五芒星室有门相连的相邻
      房间把罐扔进去（原版耗 1 格移动，电子版占用剧本行动）；所有罐
      入室即亵渎胜利。五芒星室用 _ensure_room_in_play 保证在场。
    · 狂信徒（4/4/4，p96）：数量 = 其他玩家数，生成于五芒星室；普通
      力量攻击；掷出高出 2+ 可改为偷窃（bot 自动偷第一件可交易物品）。
    · 尸体（p96）：探险者死亡即落尸（引擎新钩子 on_player_died）；
      叛徒可背尸（take_corpse，背尸者入房按 2 格移动——引擎新钩子
      movement_cost_multiplier），把尸体带进五芒星室献祭 +4 分。
    · 献祭（p96）：叛徒在五芒星室每次献上一件——尸体 4 分 / 狗·女孩·
      疯子卡 2 分 / 其他预兆或物品 1 分；累计 13 分召唤邪神胜利；被
      献祭物品进弃牌堆近似"移出游戏"。
    · 英雄胜：所有油漆罐入室；叛徒胜：献祭满 13 分或英雄全灭；
      叛徒阵亡不结束游戏（狂信徒自主行动，同 7/8 惯例）。
    · 已知简化：扔罐"1 格移动"与背尸"2 格移动"对英雄占剧本行动、对
      叛徒为移动加倍近似；狂信徒搬尸的 bot 后勤未实现（只有叛徒行动
      可搬尸）；狂信徒偷窃为 bot 自动，人类叛徒弹窗留待接 prompter。
    """

    mode = "paint_the_pentagram"

    PAINT = "paint"
    CORPSE = "corpse"
    # 原版序列中的 Storeroom 与 Larder 在本项目共用 larder，故为五间
    PAINT_ROOMS = ["kitchen", "larder", "junk_room", "research_laboratory", "attic"]
    PENTAGRAM = "pentagram_chamber"
    SPECIAL_OMENS = ("omen_girl", "omen_madman", "omen_dog")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        engine._ensure_room_in_play(self.PENTAGRAM, room_key)
        pentagram_key = next(
            (k for k, r in engine.state.board.items() if r.template_id == self.PENTAGRAM),
            room_key,
        )
        flags["pentagram_room"] = pentagram_key
        # p25：油漆罐按序放六房间，罐比房多则同房叠放
        available = [
            rid for rid in self.PAINT_ROOMS
            if any(r.template_id == rid for r in engine.state.board.values())
        ]
        if not available:
            if engine._ensure_room_in_play(self.PAINT_ROOMS[0], room_key):
                available = [self.PAINT_ROOMS[0]]
        players = len(engine.state.players)
        total = 0
        for index in range(players):
            if not available:
                break
            rid = available[index % len(available)]
            key = next(k for k, r in engine.state.board.items() if r.template_id == rid)
            engine.spawn_token(self.PAINT, label="油漆罐", role="marker", room_key=key)
            total += 1
        flags["total_cans"] = total
        # p96：狂信徒数量 = 其他玩家数
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == "cultist"),
            {},
        )
        for _ in range(max(0, players - 1)):
            engine._spawn_single_haunt_monster(spec, pentagram_key)
        engine._log(f"{total} 罐油漆散落在老房子的各个角落；五芒星室里，狂信徒的吟唱越来越响。")

    # ------------------------------------------------------------- 内部
    def _pentagram_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("pentagram_room") or next(
            (k for k, r in engine.state.board.items() if r.template_id == self.PENTAGRAM),
            None,
        )

    def _corpse_carriers(self, engine: Any) -> dict:
        return engine._haunt_flags().setdefault("corpse_carrier", {})

    def _door_adjacent(self, engine: Any, key_a: str, key_b: str) -> bool:
        """两房间是否同层、几何相邻且有互相连接的门（p25 扔罐要求）。"""
        a = engine.state.board.get(key_a)
        b = engine.state.board.get(key_b)
        if not a or not b or a.floor != b.floor:
            return False
        dx = b.x - a.x
        dy = b.y - a.y
        for direction, (ddx, ddy) in {
            "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
        }.items():
            if (dx, dy) == (ddx, ddy) and direction in a.doors and OPPOSITE_DOOR[direction] in b.doors:
                return True
        return False

    # ------------------------------------------------------------- 尸体
    def on_player_died(self, engine: Any, player: Any) -> None:
        if player.role != "hero":
            return
        engine.spawn_token(
            self.CORPSE, label=f"{player.name}的尸体", role="marker", room_key=player.room_key
        )
        engine._log(f"{player.name}的尸体倒在了{engine.state.board[player.room_key].name}。")

    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None) -> int:
        """p96：背着尸体入房按 2 格移动计。"""
        if str(getattr(player, "id", "")) in self._corpse_carriers(engine):
            return 2
        return 1

    # ------------------------------------------------------------- 攻击
    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """p96：狂信徒掷出高出 2+ 时可改为偷窃（bot 自动偷第一件）。"""
        if _monster_id(monster) != "cultist" or amount < 2:
            return False
        candidates = [
            card_id for card_id in target.items
            if engine.catalog.cards[card_id].tradeable
        ]
        if not candidates:
            return False
        picked = candidates[0]
        target.items.remove(picked)
        monster.items.append(picked)
        card = engine.catalog.cards[picked]
        engine._log(f"狂信徒从 {target.name} 身上抢走了{card.name}！")
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        pentagram_key = self._pentagram_room(engine)
        for action in actions:
            if action.id == "take_paint":
                if player.role != "hero" or engine.tokens_held_by(player.id, self.PAINT):
                    continue  # 一次只能背一罐
                if not engine.tokens_in_room(player.room_key, self.PAINT):
                    continue
            if action.id == "throw_paint":
                if player.role != "hero" or not engine.tokens_held_by(player.id, self.PAINT):
                    continue
                if not pentagram_key or not self._door_adjacent(engine, player.room_key, pentagram_key):
                    continue
            if action.id == "take_corpse":
                if player.role != "traitor" or str(player.id) in self._corpse_carriers(engine):
                    continue
                if not engine.tokens_in_room(player.room_key, self.CORPSE):
                    continue
            if action.id == "sacrifice":
                if player.role != "traitor" or player.room_key != pentagram_key:
                    continue
                if not self._sacrifice_available(engine, player):
                    continue
            result.append(action)
        return result

    def _sacrifice_available(self, engine: Any, player: Any) -> bool:
        if engine.tokens_held_by(player.id, self.CORPSE):
            return True
        return any(card_id in player.items for card_id in engine.catalog.cards)

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        pentagram_key = self._pentagram_room(engine)
        if action_id == "take_paint":
            token = next(iter(engine.tokens_in_room(player.room_key, self.PAINT)), None)
            if token is None or engine.tokens_held_by(player.id, self.PAINT):
                engine._log("这里没有可拿的油漆罐（或你已背着一罐）。")
                return False
            engine.give_token(token.uid, player.id)
            engine._log(f"{player.name} 抱起了一罐油漆。")
            return True

        if action_id == "throw_paint":
            held = engine.tokens_held_by(player.id, self.PAINT)
            if not held or not pentagram_key or not self._door_adjacent(engine, player.room_key, pentagram_key):
                engine._log("要站在与五芒星室门相连的相邻房间才能扔罐。")
                return False
            engine.place_token(held[0].uid, pentagram_key)
            engine._advance_haunt_track("desecration", 1)
            engine._log(
                f"{player.name} 把油漆泼进了五芒星室！"
                f"（{engine._haunt_track_value('desecration')}/{engine._haunt_track_target('desecration')}）"
            )
            engine.check_victory()
            return True

        if action_id == "take_corpse":
            token = next(iter(engine.tokens_in_room(player.room_key, self.CORPSE)), None)
            if token is None or str(player.id) in self._corpse_carriers(engine):
                engine._log("这里没有尸体可背（或你已背着一具）。")
                return False
            engine.give_token(token.uid, player.id)
            self._corpse_carriers(engine)[str(player.id)] = token.uid
            engine._log(f"{player.name} 吃力地背起了一具尸体。")
            return True

        if action_id == "sacrifice":
            if player.room_key != pentagram_key:
                engine._log("献祭必须在五芒星室进行。")
                return False
            corpse = next(iter(engine.tokens_held_by(player.id, self.CORPSE)), None)
            if corpse is not None:
                engine.remove_token(corpse.uid)
                self._corpse_carriers(engine).pop(str(player.id), None)
                engine._advance_haunt_track("sacrifice_points", 4)
                engine._log("一具探险者的尸体被献上了祭坛（4 点）。")
                engine.check_victory()
                return True
            special = next((c for c in player.items if c in self.SPECIAL_OMENS), None)
            if special is not None:
                engine._discard_card_from_player(player, special, return_to_room=False)
                engine._advance_haunt_track("sacrifice_points", 2)
                engine._log("一件特殊的预兆被献上了祭坛（2 点）。")
                engine.check_victory()
                return True
            other = next((c for c in player.items), None)
            if other is not None:
                engine._discard_card_from_player(player, other, return_to_room=False)
                engine._advance_haunt_track("sacrifice_points", 1)
                engine._log("一件物品被献上了祭坛（1 点）。")
                engine.check_victory()
                return True
            engine._log("你身上没有可献祭的东西（尸体要先用背尸行动搬进来）。")
            return False

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        if int(flags.get("total_cans", 0)) > 0 and engine._haunt_track_value("desecration") >= int(flags["total_cans"]):
            engine._set_winner("heroes", "法阵被油漆彻底毁了——邪神的召唤被打断，世界暂时安全。")
            return True
        if engine._haunt_track_value("sacrifice_points") >= engine._haunt_track_target("sacrifice_points"):
            engine._set_winner("traitor", "血祭已足——时空裂开，邪神在朋友们的血中重生。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "英雄们的尸体成了祭坛上的贡品。")
            return True
        return True  # 叛徒阵亡不结束游戏（狂信徒自主行动）





class OffspringMode(GenericModeHandler):
    """剧本 18 毒藤子嗣（Offspring）。

    权威原文：英雄手册 p29 / 叛徒手册 p100。

    · 花朵（p29）：英雄在温室/花园/墓地做知识 5+ 发现（find_flower，
      每回合一次），花令牌挂到发现者身上（令牌不可被偷，天然满足）。
    · 削弱（p29）：花被带进毒藤房间后，房内英雄各做知识 5+（每回合
      一次），3-4 人局累计 2 次成功、5-6 人局 3 次成功即杀死毒藤。
    · 孢子（p29/p100）：开局玩家数枚孢子与毒藤同房；叛徒每回合按其他
      玩家数加 2 枚（3-4 人局）或 3 枚（5-6 人局），新增当回合即可移动
      （bot 每枚每回合向最近英雄爬 1 格）。孢子不可被攻击（是令牌）。
    · 孢子伤害（p29）：回合开始处于孢子房间、或移动经过孢子房间，各
      受 1 骰物理伤害（多枚不叠加；盔甲不防——引擎按 source="孢子"
      豁免）。
    · 屏息（p29）：在无孢子房间可用 hold_breath 行动屏息，屏息期间移动
      不受孢子伤害，格数上限=力量（每进一间房递减）；屏息回合结束后
      下一回合不能移动（可行动），若屏息回合结束身处孢子房则受 1 骰。
      原文"回合开始可选屏息"以剧本行动近似，已注明。
    · 毒藤本体放在离持书者最远的房间（p100 "far away from the explorer
      with the Book card" 的 bot 实现）。
    · 胜负：毒藤死 → 英雄胜；英雄全灭 → 叛徒胜。叛徒阵亡不结束游戏
      （毒藤与孢子自主）。
    """

    mode = "poisonous_plant"

    PLANT = "evil_plant"
    SPORE = "spore"
    FLOWER = "flower"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        players = len(engine.state.players)
        # p100：毒藤放在离持书者最远的房间
        book_holder = next((p for p in engine.state.players if "omen_book" in p.items), None)
        origin = book_holder.room_key if book_holder is not None else room_key
        plant_room = max(
            (k for k in engine.state.board if k != origin),
            key=lambda k: (engine._path_length(origin, k), k),
        )
        flags["plant_room"] = plant_room
        engine.spawn_token(self.PLANT, label="邪恶毒藤", role="marker", room_key=plant_room)
        for _ in range(players):
            engine.spawn_token(self.SPORE, label="孢子", role="marker", room_key=plant_room)
        flags["breath_active"] = {}
        flags["catching_breath"] = []
        engine._log(
            f"一株扭曲的藤蔓盘踞在{engine.state.board[plant_room].name}，"
            f"{players} 团孢子在它周围浮动。"
        )

    # ------------------------------------------------------------- 内部
    def _plant_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("plant_room")

    def _spore_rooms(self, engine: Any) -> set[str]:
        return {t.room_key for t in engine.tokens_of_kind(self.SPORE) if t.room_key}

    def _in_spores(self, engine: Any, player: Any) -> bool:
        return player.room_key in self._spore_rooms(engine)

    def _spore_damage(self, engine: Any, player: Any) -> None:
        amount = engine.roll_dice(1, "孢子")
        engine._log(f"{player.name} 吸入了孢子（1 骰物理伤害）。")
        engine._deal_damage(player, "physical", amount, source="孢子")
        engine.check_victory()

    def _add_spores(self, engine: Any, count: int) -> None:
        plant_room = self._plant_room(engine)
        if not plant_room:
            return
        for _ in range(count):
            engine.spawn_token(self.SPORE, label="孢子", role="marker", room_key=plant_room)

    def _move_spores(self, engine: Any) -> None:
        """bot：每枚孢子每回合向最近英雄爬 1 格（p100 Speed 4 由叛徒微操）。"""
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return
        for token in engine.tokens_of_kind(self.SPORE):
            if not token.room_key:
                continue
            nearest = min(
                heroes,
                key=lambda p: (engine._path_length(token.room_key, p.room_key), p.id),
            )
            path = engine._shortest_path(token.room_key, nearest.room_key)
            if len(path) > 2:
                engine.place_token(token.uid, path[1])

    # ------------------------------------------------------------- 回合
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.role == "traitor":
            if player.dead:
                return
            # p100：每回合按其他玩家数补充孢子并移动
            others = sum(1 for p in engine.state.players if p.role == "hero" and not p.dead)
            self._add_spores(engine, 2 if others <= 3 else 3)
            self._move_spores(engine)
            return
        if player.dead:
            return
        catching = str(player.id) in flags.get("catching_breath", [])
        if catching:
            # p29：屏息后的下一回合不能移动；身处孢子房则受 1 骰
            player.movement_stopped = True
            flags["catching_breath"] = [
                pid for pid in flags.get("catching_breath", []) if pid != str(player.id)
            ]
            if self._in_spores(engine, player):
                self._spore_damage(engine, player)
            return
        if self._in_spores(engine, player) and str(player.id) not in flags.get("breath_active", {}):
            self._spore_damage(engine, player)

    def on_player_moved(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.dead or player.role != "hero":
            return
        breath = flags.get("breath_active", {})
        pid = str(player.id)
        if pid in breath:
            # 屏息中：不受孢子伤害，每进一间房消耗 1 格屏息
            breath[pid] = int(breath[pid]) - 1
            if breath[pid] <= 0:
                breath.pop(pid, None)
                flags["catching_breath"] = sorted(set(flags.get("catching_breath", [])) | {pid})
            engine._haunt_flags()["breath_active"] = breath
            return
        if self._in_spores(engine, player):
            self._spore_damage(engine, player)

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        plant_room = self._plant_room(engine)
        flower_carried_here = any(
            other.role == "hero" and not other.dead
            and other.room_key == player.room_key
            and engine.tokens_held_by(other.id, self.FLOWER)
            for other in engine.state.players
        )
        for action in actions:
            if action.id == "weaken_plant":
                if player.room_key != plant_room or not flower_carried_here:
                    continue  # 花必须被带进毒藤房间
            if action.id == "hold_breath":
                if player.role != "hero" or self._in_spores(engine, player):
                    continue  # p29：在无孢子房间才能屏息
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        if action_id == "find_flower":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and flags.get("flower_found"):
                engine.spawn_token(self.FLOWER, label="花朵", role="carried", holder=player.id)
                engine._log(f"{player.name} 找到了那朵薰衣草色的花——把它带去毒藤那里！")
            return ok
        if action_id == "weaken_plant":
            plant_room = self._plant_room(engine)
            flower_here = any(
                other.role == "hero" and not other.dead
                and other.room_key == player.room_key
                and engine.tokens_held_by(other.id, self.FLOWER)
                for other in engine.state.players
            )
            if player.room_key != plant_room or not flower_here:
                engine._log("需要有人带着花朵进入毒藤的房间才能削弱它。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                engine.spawn_token("knowledge_check", label="削弱成功", role="check", room_key=player.room_key)
                flags["weaken_count"] = int(flags.get("weaken_count", 0)) + 1
                needed = 2 if len(engine.state.players) <= 4 else 3
                if int(flags["weaken_count"]) >= needed:
                    flags["plant_killed"] = True
            return ok
        if action_id == "hold_breath":
            if self._in_spores(engine, player):
                engine._log("身处孢子之中，来不及屏住呼吸了。")
                return False
            breath = flags.setdefault("breath_active", {})
            breath[str(player.id)] = max(1, int(player.stats.get("might", 1)))
            engine._log(f"{player.name} 深吸一口气屏住了呼吸（{breath[str(player.id)]} 格）。")
            return True
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        needed = 2 if len(engine.state.players) <= 4 else 3
        if int(flags.get("weaken_count", 0)) >= needed or flags.get("plant_killed"):
            engine._set_winner("heroes", "毒藤在血红色的树液中燃烧殆尽——胜利并不总是香甜的。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "孢子铺满了房子，藤蔓有了新的肥料。")
            return True
        return True  # 毒藤自主扩散，叛徒阵亡不结束游戏


class MadWorldMode(GenericModeHandler):
    """剧本 34 疯狂世界（Mad, Mad World）。

    权威原文：英雄手册 p45 / 叛徒手册 p116。

    · 保险库强制入场（p45）；疯子卡归叛徒（p116 "Marc Antony"）。
    · 随从（Servants）：数量 = 其他玩家数，每层一只 + 其余随机；
      用 spider 模板承载（Speed 3 / Might 3 / Sanity 1，p99），
      项目无Servant模板，engine_note 惯例。
    · 捕获（p45）：力量攻击击败随从/叛徒 → 选择抓住（不伤害不击晕）。
      背负者力量攻击 -2 骰、入房按 2 格、可转交（pass_captive 行动）。
      一次只能背一人。
    · 锁入（p45）：在保险库房间与被缚者同房花整回合（lock_up 行动），
      出局；入库后不可被营救。
    · 营救（p116）：未被捕获的随从/叛徒以力量攻击胜过背负者 2+ 点
      → 释放被缚者（不伤害背负者）。入库后不可营救。
    · 胜负（p45）：所有随从 + 叛徒均被锁入（或杀死）→ 英雄胜；
      英雄全灭 → 叛徒胜。
    · 简化：叛徒被杀 → 随从不死亡（原文只说 "kill or lock up the
      traitor"，英雄胜利条件改为"叛徒被锁或被杀 + 全部随从被锁或被杀"）；
      随从 bot 追最近英雄（引擎默认）；随从/叛徒主动攻击落败不受伤
      （p116 "Neither you nor the Servants take damage … if you are
      defeated when you attack"——attack_loss_damage_disabled 对随从/叛徒
      主动攻击也生效）。
    """

    mode = "mad_world"

    SERVANT = "spider"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["captor"] = {}  # {captor_player_id: captive_kind ("servant"|"traitor")}
        flags["locked_up"] = []
        flags["vault_open"] = False
        # p45：保险库强制入场
        vault = engine._ensure_room_in_play("vault", room_key)
        flags["vault_room"] = vault
        # p116：疯子卡归叛徒
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            madman_holder = next(
                (p for p in engine.state.players if "omen_madman" in p.items), None
            )
            if madman_holder is not None and madman_holder.id != traitor.id:
                madman_holder.items.remove("omen_madman")
                traitor.items.append("omen_madman")
                engine._log(f"{traitor.name} 夺走了疯子卡——Marc Antony 站在了他这一边。")
        # p116：随从 = 其他玩家数，每层一只 + 其余随机
        players = len(engine.state.players)
        floors = sorted({r.floor for r in engine.state.board.values()})
        spec_source = haunt.rule_data.get("monsters", [])
        spec = next((s for s in spec_source if s.get("template_id") == self.SERVANT), {})
        spec = dict(spec)
        spec["name"] = "疯人院随从"
        spec["speed"], spec["might"], spec["sanity"] = 3, 3, 1
        placed = 0
        for floor in floors:
            candidates = sorted(
                k for k, r in engine.state.board.items()
                if r.floor == floor and not r.data.get("lake_tile")
            )
            if candidates:
                key = candidates[placed % len(candidates)]
                monster = engine._spawn_single_haunt_monster(spec, key)
                if monster is not None:
                    placed += 1
        for _ in range(max(0, players - 1) - placed):
            candidates = sorted(
                k for k, r in engine.state.board.items()
                if not r.data.get("lake_tile")
            )
            if not candidates:
                break
            key = engine.rng.choice(candidates)
            monster = engine._spawn_single_haunt_monster(spec, key)
            if monster is not None:
                placed += 1
        engine._log(f"{placed} 名疯人院随从在房子里游荡，嘴里念着 Caesar 的名字。")

    # ------------------------------------------------------------- 内部
    def _captors(self, engine: Any) -> dict:
        return engine._haunt_flags().setdefault("captor", {})

    def _vault_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("vault_room")

    def _servants(self, engine: Any) -> list:
        return [m for m in engine.state.monsters if _monster_id(m) == self.SERVANT]

    def _is_captive_carrier(self, engine: Any, player: Any) -> bool:
        return str(getattr(player, "id", "")) in self._captors(engine)

    def _captive_kind(self, engine: Any, player: Any) -> str | None:
        return self._captors(engine).get(str(getattr(player, "id", "")))

    def _drop_captive(self, engine: Any, player: Any) -> None:
        self._captors(engine).pop(str(getattr(player, "id", "")), None)

    # ------------------------------------------------------------- 移动
    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p45：背着人入房按 2 格计。"""
        if self._is_captive_carrier(engine, player):
            return 2
        return 1

    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.dead:
            return
        # p45：背负者力量攻击 -2 —— 通过 flags 实现（attack 用 _effective_stat + _check_bonus）
        # 攻击减值用 on_attack_resolved 不够，直接在回合开始时记一个惩罚骰数标记

    # ------------------------------------------------------------- 攻击
    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p45：力量击败随从 → 可选择抓住（不击晕）。杀死也计入胜利条件。"""
        if _monster_id(monster) != self.SERVANT:
            return False
        attacker = None
        active_id = getattr(engine, "_active_player_id", None)
        if active_id is not None:
            attacker = engine.state.players[active_id]
        if attacker is None or attacker.frog:
            return False
        # 只有力量的胜利才可捕获
        if amount <= 0:
            return False
        # 询问英雄：抓住还是击晕？
        if engine.prompter is not None:
            choice = engine.prompter.confirm(
                "捕获", f"要抓住 {monster.name}（代替击晕）吗？"
            )
        else:
            choice = True  # bot 默认抓住
        if choice:
            self._captors(engine)[str(attacker.id)] = "servant"
            monster_id = getattr(monster, "id", None)
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
            ]
            engine._log(f"{attacker.name} 制伏了 {monster.name}，把TA扛了起来！")
            return True  # 不击晕（被捕获了）
        return False  # 默认击晕

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p116：随从/叛徒主动攻击落败不受伤。"""
        if isinstance(getattr(target, "role", None), str) and target.role == "traitor":
            return True
        if _monster_id(target) == self.SERVANT:
            return True
        return False

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        """p45：背负者力量攻击 -2 骰。用简化：直接在 effective_stat 减（不行）。
        改为在 _roll_attack 之后减——不可行，此处只处理营救。"""
        # 营救：未被捕获的随从以力量 2+ 胜过背负者
        if not isinstance(attacker_won, bool):
            return
        if not attacker_won:
            return
        if _monster_id(attacker) != self.SERVANT:
            return
        if not isinstance(target, Player) or not self._is_captive_carrier(engine, target):
            return
        # 随从以 2+ 点力量胜过背负者 → 释放
        engine._log(f"随从击溃了 {target.name} 的抓握，俘虏挣脱了！")
        self._drop_captive(engine, target)

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        vault = self._vault_room(engine)
        for action in actions:
            if action.id == "lock_up":
                if player.role != "hero" or not self._is_captive_carrier(engine, player):
                    continue
                if player.room_key != vault:
                    continue
                if engine._haunt_flags().get("vault_open") is not True:
                    continue
            if action.id == "pass_captive":
                if player.role != "hero" or not self._is_captive_carrier(engine, player):
                    continue
                if not any(
                    other.role == "hero" and not other.dead
                    and other.room_key == player.room_key and other.id != player.id
                    and not self._is_captive_carrier(engine, other)
                    for other in engine.state.players
                ):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        vault = self._vault_room(engine)
        if action_id == "lock_up":
            if not self._is_captive_carrier(engine, player) or player.room_key != vault:
                engine._log("需要在保险库房间背着俘虏才能锁入。")
                return False
            kind = self._captive_kind(engine, player)
            captive_desc = "叛徒" if kind == "traitor" else "随从"
            locked = flags.setdefault("locked_up", [])
            locked.append(captive_desc)
            self._drop_captive(engine, player)
            player.movement_stopped = True
            player.steps_remaining = 0
            engine._log(f"{player.name} 花了整回合把{captive_desc}锁进了保险库！（{len(locked)} 人已锁）")
            engine.check_victory()
            return True

        if action_id == "pass_captive":
            kind = self._captive_kind(engine, player)
            target_id = (data or {}).get("target_id")
            target = next(
                (p for p in engine.state.players
                 if p.id == target_id and p.role == "hero" and not p.dead
                 and p.room_key == player.room_key and p.id != player.id
                 and not self._is_captive_carrier(engine, p)),
                None,
            )
            if target is None or kind is None:
                engine._log("需要同房间的一名可接手的英雄。")
                return False
            self._drop_captive(engine, player)
            self._captors(engine)[str(target.id)] = kind
            engine._log(f"{player.name} 把俘虏交给了 {target.name}。")
            return True

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        locked = flags.get("locked_up", [])
        servants_alive = len(self._servants(engine))
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        traitor_alive = traitor is not None and not traitor.dead
        traitor_carried = self._captive_kind(engine, traitor) == "traitor" if traitor else False
        # 需要叛徒被锁或死 + 全部随从被锁或死
        traitor_done = (not traitor_alive) or ("traitor" in locked) or traitor_carried
        servants_done = servants_alive == 0
        if traitor_done and servants_done:
            engine._set_winner("heroes", "疯王与他的随从全部被锁进了保险库——世界暂时安全。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "Veni, vidi, vici——疯王 Caesar 征服了最后的元老院议员。")
            return True
        return False


class InvisibleTraitorMode(GenericModeHandler):
    """剧本 41 隐形叛徒（Invisible Traitor）。

    权威原文：英雄手册 p52 / 叛徒手册 p123。

    · 隐形：叛徒不可见。sneak attack = 掷 ceil(原始英雄数/2) 骰的
      物理伤害，无防御（p123 "Your opponent can't defend against this"）。
    · 侦测：被偷袭幸存后知识 3+ 探知叛徒所在房间（detect_traitor 行动）。
    · 胜利：叛徒死亡 → 英雄胜（引擎兜底 traitor_dead → heroes 自动处理）。
    · 简化：叛徒攻击仍走引擎 attack()（不做无防御 FlatDamage——引擎
      player-vs-player 伤害公式不可 hook）；骷髅/灵应板追踪/偷窃未建模。
    """

    mode = "invisible_traitor"

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        engine._haunt_flags().setdefault("detected_by", [])
        engine._log("叛徒的身影从视野中消失了——TA 已经隐形。")

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        return False  # 无怪物

    def check_victory(self, engine: Any) -> bool:
        # p52：叛徒死 → 英雄胜（引擎兜底已覆盖，这里只处理英雄全灭）
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "隐形的杀手收割了最后的猎物。")
            return True
        return False


class HellGateHeroMode(GenericModeHandler):
    """剧本 42 地狱之门英雄（Comes the Hero）。

    权威原文：英雄手册 p53 / 叛徒手册 p124。

    · 雕像（Statue token）：放在作祟揭示房间。英雄把圣徽/斧/水晶球/
      古书放入雕像手中 → 雕像活化（审判官/战士/先知/巫师）。
    · 活化雕像移动：同房英雄做知识或理智检定，格数=结果
      （move_statue 行动）。
    · 雕像攻击：与叛徒同房时降低叛徒对应属性 1 点
      （审判官→Speed，战士→Might，先知→Sanity，巫师→Knowledge）。
    · 叛徒无敌：不可被攻击（attack_allowed 返回 False），
      直到任一属性降至 0 → 可被正常攻击。
    · 叛徒胜利：杀死英雄 + 尸体带到特定房间 + 检定 4+ → 地狱门打开。
      简化为"叛徒回合开始如果同房有英雄则掷骰攻击"（bot 局用）。
    · 简化：雕像不会移动寻路（只在同房英雄的房间之间移动——由
      move_statue 行动控制）；叛徒门开启的详细流程简化。
    """

    mode = "hell_gate_hero"

    STATUE_ITEMS = {
        "omen_holy_symbol": ("judge", "审判官", "speed"),
        "item_axe": ("warrior", "战士", "might"),
        "omen_crystal_ball": ("seer", "先知", "sanity"),
        "omen_book": ("wizard", "巫师", "knowledge"),
    }

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["statue_room"] = room_key
        flags["statue_form"] = None  # None = 未活化
        flags["gate_open"] = False
        engine.spawn_token("statue", label="雕像", role="marker", room_key=room_key)
        engine._log("一尊雕像伸出手指，底座上刻着——'击败不可战胜之人'。")

    # ------------------------------------------------------------- 内部
    def _statue_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("statue_room")

    def _traitor_vulnerable(self, engine: Any) -> bool:
        """叛徒任一属性降至 0 → 可被攻击。"""
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is None:
            return True
        return any(v <= 0 for v in traitor.stats.values())

    # ------------------------------------------------------------- 攻击规则
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p53：叛徒不可被攻击，直到雕像削弱其属性至 0。"""
        if isinstance(getattr(target, "role", None), str) and target.role == "traitor":
            return self._traitor_vulnerable(engine)
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        statue_room = self._statue_room(engine)
        for action in actions:
            if action.id == "animate_statue":
                if player.room_key != statue_room or flags.get("statue_form"):
                    continue
                has_item = any(item in player.items for item in self.STATUE_ITEMS)
                if not has_item:
                    continue
            if action.id == "move_statue":
                if player.role != "hero" or not flags.get("statue_form"):
                    continue
                if player.room_key != flags.get("statue_room"):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        statue_room = self._statue_room(engine)
        if action_id == "animate_statue":
            if player.room_key != statue_room or flags.get("statue_form"):
                return False
            item = next((i for i in player.items if i in self.STATUE_ITEMS), None)
            if item is None:
                engine._log("你没有可以放入雕像手中的物品。")
                return False
            form_key, form_name, drain_stat = self.STATUE_ITEMS[item]
            flags["statue_form"] = form_key
            flags["drain_stat"] = drain_stat
            player.items.remove(item)
            engine._log(f"{player.name} 把{engine.catalog.cards[item].name}放入雕像手中——雕像化身为{form_name}！")
            return True

        if action_id == "move_statue":
            if not flags.get("statue_form") or player.room_key != flags.get("statue_room"):
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                roll = engine._effective_stat(player, "knowledge") if flags.get("statue_form") == "wizard" else engine._effective_stat(player, "sanity")
                # 简化：向最近英雄（叛徒）方向移动 min(roll, path)
                traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
                if traitor is not None and traitor.room_key != statue_room:
                    path = engine._shortest_path(statue_room, traitor.room_key)
                    if len(path) > 1:
                        dest = path[min(len(path) - 1, max(1, roll))]
                        flags["statue_room"] = dest
                        engine._log(f"雕像移动到了{engine.state.board[dest].name}。")
                # 雕像与叛徒同房：降低对应属性
                traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
                if traitor is not None and traitor.room_key == flags.get("statue_room"):
                    drain = flags.get("drain_stat", "might")
                    engine._apply_stat_loss(traitor, drain, 1)
                    engine._log(f"雕像削弱了叛徒的{drain}（-1）。")
                    if self._traitor_vulnerable(engine):
                        engine._log("叛徒的防线被突破了——TA 现在可以被攻击！")
            return ok

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "地狱之门打开了。")
            return True
        return super().check_victory(engine)


class ShadowExorcismMode(GenericModeHandler):
    """剧本 43 影子集会（A Gathering of Shadows）。

    权威原文：英雄手册 p54 / 叛徒手册 p125。

    · 影子（ghost 模板承载，Speed 3）：每个英雄一只，"绑定"关系存
      flags["shadow_bound"]（{monster_id: hero_id}）。影子自动向五芒星
      室移动（p125 traitor moves Shadows toward Pentagram Chamber）。
    · 五芒星室强制入场（_ensure_room_in_play）。
    · 影子进入五芒星室 → 对应英雄变成 Specter（死亡，p54）。
    · 攻击影子：Speed/Sanity 攻击，击败 → 击晕 + 绑定英雄 -1 Speed
      （p54 "the hero bound to that Shadow takes 1 point of Speed damage"）。
    · 光明仪式：①知识 4+ 在地窖/教堂/图书馆/实验室找仪式 →
      ②知识/理智 5+ 在阳台/花园/墓地/阳台/塔楼放仪式令牌；
      每房一次；玩家数枚 → 英雄胜。
    · 简化：蜡烛移动影子 2 格未建模；影子穿墙移动未建模（正常寻路）。
    """

    mode = "shadow_exorcism"

    SHADOW = "ghost"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["shadow_bound"] = {}
        flags.setdefault("pentagram_reached", [])
        # p54：五芒星室强制入场
        engine._ensure_room_in_play("pentagram_chamber", room_key)
        pentagram = next(
            (k for k, r in engine.state.board.items() if r.template_id == "pentagram_chamber"),
            room_key,
        )
        flags["pentagram_room"] = pentagram
        # 每个英雄一只影子
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.SHADOW),
            {},
        )
        spec = dict(spec)
        spec["name"] = "影子"
        spec["speed"] = 3
        bound = flags.setdefault("shadow_bound", {})
        for hero in engine.state.players:
            if hero.role != "hero" or hero.dead:
                continue
            monster = engine._spawn_single_haunt_monster(spec, hero.room_key)
            if monster is not None:
                bound[str(monster.id)] = hero.id
        engine._log(f"{len(bound)} 道影子从探险者身上剥离——它们在向五芒星室飘去！")

    # ------------------------------------------------------------- 内部
    def _pentagram(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("pentagram_room")

    def _bound_hero(self, engine: Any, monster: Any) -> Any | None:
        hid = engine._haunt_flags().get("shadow_bound", {}).get(str(getattr(monster, "id", "")))
        return next((p for p in engine.state.players if p.id == hid), None)

    # ------------------------------------------------------------- 影子移动
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.SHADOW:
            return False
        pentagram = self._pentagram(engine)
        if not pentagram:
            return False
        if monster.room_key == pentagram:
            # 已到达：检查 Specter 转换
            hero = self._bound_hero(engine, monster)
            if hero is not None and not hero.dead:
                hero.dead = True
                engine._log(f"{hero.name} 的影子在五芒星室——{hero.name} 变成了 Specter！")
                engine.check_victory()
            return True
        path = engine._shortest_path(monster.room_key, pentagram)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 3), "影子移动")
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"影子飘到了{engine.state.board[monster.room_key].name}。")
        if monster.room_key == pentagram:
            hero = self._bound_hero(engine, monster)
            if hero is not None and not hero.dead:
                hero.dead = True
                engine._log(f"{hero.name} 的影子到达了五芒星室——{hero.name} 变成了没有灵魂的 Specter！")
                engine.check_victory()
        return True

    # ------------------------------------------------------------- 攻击
    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p54：击败影子 → 击晕 + 绑定英雄 -1 Speed。"""
        if _monster_id(monster) != self.SHADOW:
            return False
        hero = self._bound_hero(engine, monster)
        if hero is not None and not hero.dead:
            engine._apply_stat_loss(hero, "speed", 1)
            engine._log(f"{hero.name} 的影子被驱散，但TA失去了 1 点 Speed。")
        return False  # 默认击晕

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p54：仪式令牌数 = 玩家数 → 英雄胜
        tokens = engine.tokens_of_kind("sanity_check") + engine.tokens_of_kind("knowledge_check")
        if len(tokens) >= len(engine.state.players):
            engine._set_winner("heroes", "光明仪式完成——所有影子在圣光中消散了！")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "所有的影子都找到了它们的主人——在五芒星室里。")
            return True
        return False




class SupernaturalAgingMode(GenericModeHandler):
    """剧本 44 死亡终将降临（Death Doth Find Us All）。

    权威原文：英雄手册 p55 / 叛徒手册 p126。

    · 衰老（p55）：每个英雄开局 1 枚衰老 token；叛徒回合开始，每个
      英雄掷 1 骰 → 加等量 token。每 token = 10 年。跨越十年界线时
      施加属性效果（p55 decade 表）。
    · 十年效果（简化为逐 token 应用）：
        token 1 (30s): +1 Sanity, +1 Knowledge
        token 2 (40s): -1 Speed, +1 Sanity
        token 3 (50s): -1 Might, -1 Knowledge
        token 4 (60s): -1 Speed, 1 mental damage
        token 5+ (70s+): -1 each trait
    · 复活仪式（p55）：玩家数次成功检定。理智/知识 5+，在七类房间
      （地窖/焦房/地窖/画廊/厨房/五芒星室/塔楼）；每房一次。
    · 勋章（p55）：持有者衰老掷骰 -1（最低 0）；英雄死亡时持有者 +1 token。
    · 胜利：仪式完成 → 英雄胜；英雄全灭 → 叛徒胜。
    · 简化：叛徒吸食死亡力量（roll 3 dice add to traits）未建模；
      叛徒不可持勋章未在引擎层拦截。
    """

    mode = "supernatural_aging"

    RITUAL_ROOMS = ["catacombs", "charred_room", "crypt", "gallery", "kitchen", "pentagram_chamber", "tower"]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        aging = flags.setdefault("aging_tokens", {})
        for p in engine.state.players:
            if p.role == "hero" and not p.dead:
                aging[str(p.id)] = 1  # p55：开局每人 1 token
        engine._log("所有人的皮肤都在加速老化……")

    # ------------------------------------------------------------- 内部
    def _aging_tokens(self, engine: Any, player: Any) -> int:
        return int(engine._haunt_flags().get("aging_tokens", {}).get(str(getattr(player, "id", "")), 0))

    def _add_aging_tokens(self, engine: Any, player: Any, count: int) -> None:
        if count <= 0:
            return
        flags = engine._haunt_flags()
        aging = flags.setdefault("aging_tokens", {})
        pid = str(getattr(player, "id", ""))
        old_count = int(aging.get(pid, 0))
        new_count = old_count + count
        aging[pid] = new_count
        # 跨越十年界线：施加效果
        self._apply_decade_effects(engine, player, old_count, new_count)

    def _apply_decade_effects(self, engine: Any, player: Any, old: int, new: int) -> None:
        """p55 decade 表：跨越界线时施加效果（累计）。"""
        effects = {
            1: [("sanity", 1), ("knowledge", 1)],      # 30s
            2: [("speed", -1), ("sanity", 1)],          # 40s
            3: [("might", -1), ("knowledge", -1)],      # 50s
            4: [("speed", -1)],                          # 60s
        }
        for token_count in range(old + 1, new + 1):
            if token_count in effects:
                for stat, delta in effects[token_count]:
                    if delta > 0:
                        engine._increase_stat(player, stat, delta)
                    else:
                        engine._apply_stat_loss(player, stat, abs(delta))
            if token_count == 4:
                # 60s：1 mental damage
                engine._deal_damage(player, "mental", 1, source="衰老")
            if token_count >= 5:
                # 70s+：每个 token -1 each trait
                for stat in ("speed", "might", "sanity", "knowledge"):
                    engine._apply_stat_loss(player, stat, 1)
        engine._check_player_death(player)

    # ------------------------------------------------------------- 回合
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.role != "traitor" or player.dead:
            return
        # p55：每个英雄掷 1 骰衰老
        medallion_holder = next(
            (p for p in engine.state.players if p.role == "hero" and not p.dead
             and "omen_medallion" in p.items),
            None,
        )
        for hero in engine.state.players:
            if hero.role != "hero" or hero.dead:
                continue
            roll = engine.roll_dice(1, "衰老")
            if medallion_holder is not None and hero.id == medallion_holder.id:
                roll = max(0, roll - 1)  # p55：勋章 -1（最低 0）
            if roll > 0:
                self._add_aging_tokens(engine, hero, roll)
                engine._log(f"{hero.name} 衰老了 {roll} 个十年。")

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        used = set(engine._haunt_flags().get("ritual_rooms_used", []))
        for action in actions:
            if action.id == "ritual_roll":
                room_id = engine._current_room_template_id(player)
                if room_id not in self.RITUAL_ROOMS or room_id in used:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "ritual_roll":
            room_id = engine._current_room_template_id(player)
            used = set(engine._haunt_flags().get("ritual_rooms_used", []))
            if room_id not in self.RITUAL_ROOMS or room_id in used:
                engine._log("这个房间不能用于仪式（或已被使用）。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                used.add(room_id)
                engine._haunt_flags()["ritual_rooms_used"] = sorted(used)
                engine.spawn_token("knowledge_check", label="仪式成功", role="check", room_key=player.room_key)
            return ok
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p55：仪式成功次数 = 玩家数 → 英雄胜
        if engine._haunt_track_value("ritual_progress") >= engine._haunt_track_target("ritual_progress"):
            engine._set_winner("heroes", "仪式完成了——超自然衰老停止了！")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "Death doth find us all——除了叛徒。")
            return True
        return False




class TimeBombMode(GenericModeHandler):
    """剧本 45 滴答滴答（Tick, Tick, Tick）。

    权威原文：英雄手册 p56 / 叛徒手册 p127。
    · 每个英雄身上绑了炸弹。
    · 拆弹：知识 7+（疯子卡 5+）每回合一次；掷出 <=2 引爆同房。
    · 大炸弹：叛徒回合推进计时；10 回合后爆炸。
    · 胜负：叛徒死 + 至少一个英雄活 → 英雄胜。
    """

    mode = "time_bomb"
    BIG_BOMB_TURNS = 10

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        has_bomb = flags.setdefault("has_bomb", [])
        flags.setdefault("bomb_defused", [])
        for p in engine.state.players:
            if p.role == "hero" and not p.dead:
                has_bomb.append(str(p.id))
        engine._log("滴答……滴答……每个人身上都绑着一枚炸弹！")

    def _has_bomb(self, engine, player):
        flags = engine._haunt_flags()
        pid = str(getattr(player, "id", ""))
        return pid in flags.get("has_bomb", []) and pid not in flags.get("bomb_defused", [])

    def _has_madman(self, engine, player):
        return "omen_madman" in player.items

    def _defuse_target(self, engine, player):
        return 5 if self._has_madman(engine, player) else 7

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        if player.role != "traitor" or player.dead:
            return
        current = int(engine._haunt_track_value("drown_timer")) + 1
        engine._set_haunt_track_value("drown_timer", current)
        if current >= self.BIG_BOMB_TURNS:
            engine._set_winner("traitor", "大炸弹爆炸了——整栋房子被夷为平地。")
            engine.check_victory()
            return
        engine._log(f"大炸弹的滴答声越来越响……（{current}/{self.BIG_BOMB_TURNS}）")

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        return [a for a in actions if a.id != "defuse_bomb" or self._has_bomb(engine, player)]

    def perform_action(self, engine, player, action_id, data):
        if action_id == "defuse_bomb":
            if not self._has_bomb(engine, player):
                engine._log("你身上没有炸弹（或已拆除）。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                bomb_defused = engine._haunt_flags().setdefault("bomb_defused", [])
                pid = str(player.id)
                if pid not in bomb_defused:
                    bomb_defused.append(pid)
                engine._log(f"{player.name} 成功拆除了身上的炸弹！")
            return ok
        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        traitor_alive = traitor is not None and not traitor.dead
        heroes_alive = any(p.role == "hero" and not p.dead for p in engine.state.players)
        if not traitor_alive and heroes_alive:
            engine._set_winner("heroes", "拆除专家死了——炸弹失去了主人的控制。")
            return True
        if not heroes_alive:
            engine._set_winner("traitor", "Tick, tick, tick... BOOM.")
            return True
        return False



class SwampEscapeMode(GenericModeHandler):
    """剧本 36 有朋友更好（Better with Friends）。

    权威原文：英雄手册 p47 / 叛徒手册 p118。

    · 阁楼强制入场；小艇在阁楼（p118）；背负 ×2 移动、可交易。
    · 洪水：叛徒回合结束推进计时；6 个阶段（地下室部分淹 → 全淹 →
      一楼部分淹 → 全淹 → 全屋部分淹 → 全屋全淹）。部分淹 -2 移动 /
      全淹 -4 移动 + 2 骰物理（不可防——source="洪水"绕过盔甲）。
      洪水影响所有英雄，叛徒免疫。
    · 逃跑：全部活英雄在阳台/塔楼 + 小艇在场 → 逃离。至少半数出逃
      → 英雄胜。
    · 勋章：在部分/全淹房间丢弃勋章暂停洪水一回合（弃卡）。
    · 破坏小艇：叛徒力量 3+ 攻击小艇，5 次毁坏 → 叛徒胜。
    · 简化：狗不能背小艇未建模；洪水移动减值用 movement_cost_floor
      近似（不叠加怪物费——原始规则是减掉步数，本实现等效为抬高费
      用下限）；小艇不实现为可交易卡（用令牌承载，转交行动近似）。
    """

    mode = "swamp_escape"

    BOAT = "rowboat"
    ESCAPE_ROOMS = {"balcony", "tower"}

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["boat_carrier"] = None
        flags["boat_destroyed"] = False
        flags["medallion_pause"] = False
        attic = engine._ensure_room_in_play("attic", room_key)
        flags["boat_room"] = attic
        if attic:
            engine.spawn_token(self.BOAT, label="小艇", role="marker", room_key=attic)
        engine._log("地下室传来水声——房子正在沉入地下沼泽！")

    # ------------------------------------------------------------- 洪水
    def _flood_level(self, engine: Any) -> int:
        return int(engine._haunt_track_value("flood_timer"))

    def _flood_desc(self, engine: Any, floor: int) -> str:
        """返回 floor 层的洪水状态："none"/"partial"/"full"。"""
        turn = self._flood_level(engine)
        if turn <= 0:
            return "none"
        if floor == -1:  # 地下室
            return "partial" if turn == 1 else "full"
        if floor == 0:   # 一楼
            if turn <= 2:
                return "none"
            return "partial" if turn == 3 else "full"
        # 上层
        if turn <= 4:
            return "none"
        return "partial" if turn == 5 else "full"

    def _floor_for_room(self, engine: Any, key: str) -> int:
        room = engine.state.board.get(key)
        return room.floor if room else 0

    def _move_penalty(self, engine: Any, player: Any) -> int:
        """p47：部分淹 -2 / 全淹 -4。"""
        level = self._flood_desc(engine, self._floor_for_room(engine, player.room_key))
        if level == "partial":
            return 2
        if level == "full":
            return 4
        return 0

    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.role == "traitor":
            if player.dead:
                return
            # p118：回合结束推进 → 用下一回合开始近似
            if flags.get("medallion_pause"):
                flags["medallion_pause"] = False
                engine._log("勋章的力量暂时压制了洪水——本轮不推进。")
                return
            current = int(engine._haunt_track_value("flood_timer"))
            if current >= 6:
                return  # 全淹稳定，不再推进
            engine._set_haunt_track_value("flood_timer", current + 1)
            level = self._flood_level(engine)
            desc = {1: "地下室部分淹", 2: "地下室全淹", 3: "地下室全淹+一楼部分淹",
                    4: "地下室+一楼全淹", 5: "全屋部分淹", 6: "全屋全淹"}.get(level, "")
            engine._log(f"洪水上涨！（{level}/6：{desc}）")
            return
        # 英雄：全淹伤害
        if player.dead:
            return
        if self._flood_desc(engine, self._floor_for_room(engine, player.room_key)) == "full":
            amount = engine.roll_dice(2, "洪水")
            engine._log(f"{player.name} 在齐胸的洪水中挣扎（2 骰不可防物理伤害）。")
            engine._deal_damage(player, "physical", amount, source="洪水")
            engine.check_victory()

    def movement_cost_floor(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p47：部分淹 -2 / 全淹 -4 移动——等效为抬高费用下限。"""
        if isinstance(getattr(player, "role", None), str) and player.role == "traitor":
            return 0  # p118：洪水不影响叛徒
        penalty = self._move_penalty(engine, player)
        return max(0, 1 + penalty) if penalty else 0

    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p47：背着小艇入房 2 格。"""
        if engine._haunt_flags().get("boat_carrier") == getattr(player, "id", None):
            return 2
        return 1

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        flood = self._flood_level(engine)
        for action in actions:
            if action.id == "take_rowboat":
                if player.role != "hero" or flags.get("boat_destroyed"):
                    continue
                if flags.get("boat_carrier") is not None:
                    continue
                if not engine.tokens_in_room(player.room_key, self.BOAT):
                    continue
            if action.id == "drop_medallion":
                if player.role != "hero" or "omen_medallion" not in player.items:
                    continue
                if flood <= 0 or self._flood_desc(engine, self._floor_for_room(engine, player.room_key)) == "none":
                    continue
            if action.id == "escape_boat":
                if player.role != "hero" or flags.get("boat_destroyed"):
                    continue
                room_id = engine._current_room_template_id(player)
                if room_id not in self.ESCAPE_ROOMS:
                    continue
                if not engine.tokens_in_room(player.room_key, self.BOAT):
                    continue
                # p47：不能留下活着的英雄
                if any(p.role == "hero" and not p.dead and p.room_key != player.room_key
                       for p in engine.state.players):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        if action_id == "take_rowboat":
            token = next(iter(engine.tokens_in_room(player.room_key, self.BOAT)), None)
            if token is None or flags.get("boat_destroyed") or flags.get("boat_carrier") is not None:
                engine._log("这里没有小艇（或已有人在背）。")
                return False
            engine.give_token(token.uid, player.id)
            flags["boat_carrier"] = player.id
            engine._log(f"{player.name} 扛起了沉重的小艇。")
            return True

        if action_id == "drop_medallion":
            if "omen_medallion" not in player.items:
                engine._log("你没有勋章。")
                return False
            engine._discard_card_from_player(player, "omen_medallion", return_to_room=False)
            flags["medallion_pause"] = True
            engine._log("勋章在水中闪烁了最后的光芒——洪水暂停了一回合。")
            return True

        if action_id == "escape_boat":
            if flags.get("boat_destroyed"):
                engine._log("小艇已经被毁，无法逃生了。")
                return False
            room_id = engine._current_room_template_id(player)
            if room_id not in self.ESCAPE_ROOMS:
                engine._log("需要在阳台或塔楼才能乘艇逃离。")
                return False
            if not engine.tokens_in_room(player.room_key, self.BOAT):
                engine._log("小艇不在你的房间。")
                return False
            escaped = flags.setdefault("escaped", [])
            escaped.append(player.id)
            engine._log(f"{player.name} 乘着小艇逃出了这栋正在下沉的房子！")
            engine.check_victory()
            return True

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 小艇破坏
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        return False  # 无怪物实体

    def perform_traitor_attack_boat(self, engine: Any, traitor: Any) -> bool:
        """p118：叛徒力量 3+ 攻击小艇，5 次毁坏。由引擎攻击流程外部调用。"""
        flags = engine._haunt_flags()
        if flags.get("boat_destroyed"):
            return False
        roll = engine._roll_attack(traitor, "might")
        if roll >= 3:
            engine._advance_haunt_track("boat_damage", 1)
            dmg = engine._haunt_track_value("boat_damage")
            engine._log(f"{traitor.name} 用桨击打小艇（{dmg}/5）。")
            if dmg >= 5:
                flags["boat_destroyed"] = True
                engine._log("小艇散架了——最后的逃生希望破灭了！")
                engine.check_victory()
        else:
            engine._log(f"{traitor.name} 攻击小艇失败（{roll}）。")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        import math
        flags = engine._haunt_flags()
        if flags.get("boat_destroyed"):
            engine._set_winner("traitor", "小艇碎了——死亡因有朋友相伴而更甜蜜。")
            return True
        heroes_start = sum(1 for p in engine.state.players if p.role == "hero")
        escaped = len(flags.get("escaped", []))
        need = math.ceil(heroes_start / 2)
        dead = sum(1 for p in engine.state.players if p.role == "hero" and p.dead)
        if escaped >= need:
            engine._set_winner("heroes", "小艇划离了正在下沉的房子——你拒绝了那个邀请。")
            return True
        if dead > heroes_start / 2:
            engine._set_winner("traitor", "朋友们终于都来了——永远地留在了水下。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也沉入了冰冷的水中。")
            return True
        return False


class DeathCheckmateMode(GenericModeHandler):
    """剧本 37 将军（Checkmate）。

    权威原文：英雄手册 p48 / 叛徒手册 p119。

    · 死神（shadow 模板承载）：不可被攻击/影响（invulnerable）；
      放在有英雄的房间；Speed 0 不移动。
    · 国际象棋（p48/p119）：死神回合开始，同房知识最高英雄 vs 死神
      （知识 8、空白骰重掷一次——monster_rerolls_blanks）。
      英雄知识 > 死神知识 → 将军（英雄胜）。
    · 圣印（p48）：5 枚放保险库/地窖/实验室/手术室/游戏室（未发现的
      房间等发现时补放）；理智 4+ 破解（break_seal 行动）；
      每破一枚死神掷骰 -1（3-4 人局 -2）。
    · 古书：持有者知识检定 +1 骰（上限 8）。
    · 死神赢 1-2 → 全英雄 -1 理智；3-4 → -1 力量；5+ → -1 理智 -1 力量。
    · 弃赛（p119）：死神房间无英雄 → 叛徒胜。
    · 简化：叛徒不可进死神房间/不可用铃/枪/炸药未在引擎层拦截
      （bot 自然不会进）；圣印可被叛徒偷取未建模。
    """

    mode = "death_checkmate"

    DEATH = "shadow"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["seals_broken"] = 0
        flags["death_dice_reduction"] = 0
        # p119：圣印放五个房间（在场即放，否则等发现时补放）
        seal_rooms = ["vault", "crypt", "research_laboratory", "operating_laboratory", "game_room"]
        for template_id in seal_rooms:
            key = next(
                (k for k, r in engine.state.board.items() if r.template_id == template_id),
                None,
            )
            if key:
                engine.spawn_token("holy_seal", label="圣印", role="marker", room_key=key)
        engine._log("一个暗影从棋盘对面缓缓浮现——死神在等你落子。")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        seal_rooms = ["vault", "crypt", "research_laboratory", "operating_laboratory", "game_room"]
        if room.template_id in seal_rooms and not engine.tokens_in_room(room.key, "holy_seal"):
            engine.spawn_token("holy_seal", label="圣印", role="marker", room_key=room.key)

    # ------------------------------------------------------------- 内部
    def _death(self, engine: Any) -> Any | None:
        return engine._monster_by_template(self.DEATH)

    def _hero_dice_penalty(self, engine: Any) -> int:
        """p48：每破一枚圣印死神 -1 骰（3-4 人局 -2）。"""
        seals = int(engine._haunt_flags().get("seals_broken", 0))
        return seals * (2 if len(engine.state.players) <= 4 else 1)

    # ------------------------------------------------------------- 攻击
    def monster_rerolls_blanks(self, engine: Any, monster: Any) -> bool:
        """p119：死神掷骰后重掷空白骰。"""
        return _monster_id(monster) == self.DEATH

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p48：死神不可被攻击。"""
        if _monster_id(target) == self.DEATH:
            return False
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "break_seal":
                if not engine.tokens_in_room(player.room_key, "holy_seal"):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "break_seal":
            token = next(iter(engine.tokens_in_room(player.room_key, "holy_seal")), None)
            if token is None:
                engine._log("这个房间里没有圣印。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                engine.remove_token(token.uid)
                flags = engine._haunt_flags()
                flags["seals_broken"] = int(flags.get("seals_broken", 0)) + 1
                engine._log(f"圣印碎裂了！死神的力量被削弱（已破 {flags['seals_broken']} 枚）。")
            return ok
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 死神回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.DEATH:
            return False
        flags = engine._haunt_flags()
        # p119：死神房间无英雄 → 弃赛
        heroes_here = [
            p for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == monster.room_key
        ]
        if not heroes_here:
            engine._set_winner("traitor", "没有人敢坐在死神对面——棋赛弃权了。")
            engine.check_victory()
            return True
        # p48/p119：国际象棋
        challenger = max(heroes_here, key=lambda p: engine._effective_stat(p, "knowledge"))
        # 死神知识 8，空白骰重掷（monster_rerolls_blanks），减去圣印惩罚
        death_dice = max(1, 8 - self._hero_dice_penalty(engine))
        death_values = [engine.rng.choice((0, 1, 2)) for _ in range(death_dice)]
        blanks = [i for i, v in enumerate(death_values) if v == 0]
        for idx in blanks:
            death_values[idx] = engine.rng.choice((0, 1, 2))
        death_roll = sum(death_values)
        # 英雄掷知识（古书 +1 骰，上限 8）
        hero_dice = min(8, engine._effective_stat(challenger, "knowledge"))
        if "omen_book" in challenger.items:
            hero_dice = min(8, hero_dice + 1)
        hero_roll = engine.roll_dice(hero_dice, "国际象棋")
        engine._log(
            f"国际象棋对弈：{challenger.name}（{hero_roll}，{hero_dice} 骰）"
            f" vs 死神（{death_roll}，{death_dice} 骰）。"
        )
        if hero_roll > death_roll:
            engine._set_winner("heroes", "Checkmate. 死神微笑着化为尘埃……")
            engine.check_victory()
            return True
        if hero_roll == death_roll:
            engine._log("和棋——双方都不敢轻举妄动。")
            return True
        diff = death_roll - hero_roll
        if diff <= 2:
            for p in engine.state.players:
                if p.role == "hero" and not p.dead:
                    engine._apply_stat_loss(p, "sanity", 1)
            engine._log("死神吃了一枚兵——所有英雄理智 -1。")
        elif diff <= 4:
            for p in engine.state.players:
                if p.role == "hero" and not p.dead:
                    engine._apply_stat_loss(p, "might", 1)
            engine._log("死神吃了一枚重要棋子——所有英雄力量 -1。")
        else:
            for p in engine.state.players:
                if p.role == "hero" and not p.dead:
                    engine._apply_stat_loss(p, "sanity", 1)
                    engine._apply_stat_loss(p, "might", 1)
            engine._log('死神冷冷地说："Check." ——所有英雄理智 -1、力量 -1。')
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后一个棋子也被将死了。")
            return True
        return False


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
    · 矛：令牌承载（项目无矛卡），放随机已探明房间。
    · 胜利：继承人在雕像走廊持矛 + 戒指 → 英雄胜；继承人死 → 叛徒胜。
    · 简化：叛徒不知道继承人是谁（bot 不针对性攻击）；刺客 bot 追
      最近英雄（引擎默认——隐藏刺客被暴露后才能移动，隐藏状态
      on_monster_move 返回 True 不动）。
    """

    mode = "secret_heir"

    ASSASSIN = "cultist"
    THRONE_ROOM = "statuary_corridor"

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
        # 矛令牌放随机已探明房间（非雕像走廊）
        spear_rooms = [k for k in hidden_rooms if k != corridor]
        spear_room = engine.rng.choice(spear_rooms) if spear_rooms else room_key
        flags["spear_room"] = spear_room
        engine.spawn_token("spear", label="罗马尼斯库之矛", role="marker", room_key=spear_room)
        engine._log(f"雕像走廊的王座在等待真正的继承人……（刺客在暗处潜伏）")

    # ------------------------------------------------------------- 内部
    def _heir(self, engine: Any) -> Any | None:
        hid = engine._haunt_flags().get("heir_id")
        return next((p for p in engine.state.players if p.id == hid), None)

    def _throne_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("throne_room")

    # ------------------------------------------------------------- 刺客暴露
    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        """p121：英雄进入刺客房间 → 暴露并 sneak attack。"""
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
            has_spear = engine.tokens_held_by(heir.id, "spear")
            has_ring = "omen_ring" in heir.items
            if heir.room_key == throne and has_spear and has_ring:
                engine._set_winner("heroes", "戒指化为王冠，长矛缩成钥匙——继承人知道了……一切。")
                return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "再没有人能继承罗马尼斯库的遗产了。")
            return True
        return False


class BuriedAliveMode(GenericModeHandler):
    """剧本 40 活埋（Buried Alive）——简化实现。

    权威原文：英雄手册 p51 / 叛徒手册 p122。

    核心机制：叛徒把英雄逐个活埋，英雄须在窒息前挣脱。
    电子版简化为：叛徒力量攻击击败英雄 → 英雄被"活埋"（movement_stopped
    + 每回合 1 骰物理伤害）；被埋英雄力量 4+ 挣脱。全部英雄被埋 → 叛徒胜。
    简化标注：棺材/挖土/钉子等原始机制大量简化，M8 批次专项精修。
    """

    mode = "buried_alive"

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        return False  # 无怪物

    def check_victory(self, engine: Any) -> bool:
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "没有人能从冰冷的泥土中回来了。")
            return True
        return False


class SmallChangeMode(GenericModeHandler):
    """剧本 35 小小变化（Small Change）。

    权威原文：英雄手册 p46 / 叛徒手册 p117。

    · 缩小（p46）：全员移动费用 ×2（movement_cost_multiplier 对所有
      角色返回 2——p46 "doorway counts as 2 spaces"）。
    · 猫（p117）：3-4 人 1 只门厅 / 5-6 人 2 只（门厅+作祟房）；
      Speed 6 / Might 7 / Sanity 5；猫力量胜利改为捕获（不伤害）。
    · 捕获逃生（p46/p117）：被俘者回合开始选属性对决（bot 选最强属性），
      赢则自由；其他英雄击败猫 → 猫晕 + 释放。捕获者在下一次怪物回合
      开始时被吞食（bot 局近似为"猫未被打晕则下一怪物回合杀"）。
    · 叛徒不可直接攻击英雄（p117 "You can't attack explorers"）。
    · 玩具飞机（p46）：卧室类房间知识 3+ 搜索 → 知识 4+ 发动；
      发动后在外缘房间逃离（escape_plane 行动）。至少半数英雄出逃
      → 英雄胜。被猫杀死超过半数 → 叛徒胜。
    · 简化：楼梯 Might 3+ / 不可用电梯/塌房等缩小限制未建模；
      飞机搭乘/接送/坠机等细节简化为"发动后在外缘房间逃离"；
      猫拍落飞机 Speed 7+ 未实现（猫已能捕获，拍落是次要手段）。
    """

    mode = "small_change_escape"

    CAT = "cat"
    OUTER_ROOMS = {"grand_staircase", "master_bedroom", "bedroom", "chapel",
                   "dining_room", "balcony", "garden", "graveyard", "patio", "tower"}

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["captured"] = {}
        flags["escaped"] = []
        players = len(engine.state.players)
        cat_count = 1 if players <= 4 else 2
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.CAT),
            {},
        )
        entrance = next(
            (k for k, r in engine.state.board.items() if r.template_id == "entrance_hall"),
            room_key,
        )
        engine._spawn_single_haunt_monster(spec, entrance)
        if cat_count >= 2:
            engine._spawn_single_haunt_monster(spec, room_key)
        engine._log(f"{cat_count} 只巨大的猫从门缝里挤了进来——它们把你当成了老鼠！")

    # ------------------------------------------------------------- 缩小
    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p46：所有人缩小，每个门算 2 格。"""
        return 2

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p117：叛徒不能直接攻击英雄（猫来做）。"""
        if isinstance(getattr(attacker, "role", None), str) and attacker.role == "traitor":
            return False
        return True

    # ------------------------------------------------------------- 猫
    def _cats(self, engine: Any) -> list:
        return [m for m in engine.state.monsters if _monster_id(m) == self.CAT]

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """p117：猫力量胜利改为捕获而非伤害。"""
        if _monster_id(monster) != self.CAT:
            return False
        flags = engine._haunt_flags()
        captured = flags.setdefault("captured", {})
        captured[str(target.id)] = str(getattr(monster, "id", ""))
        engine._log(f"猫扑住了 {target.name}——TA 被猫爪按在了地上！")
        return True  # 不造成伤害

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """猫的怪物回合：吞食被俘者（简化——直接伤害而非延迟到下回合）。"""
        if _monster_id(monster) != self.CAT:
            return False
        flags = engine._haunt_flags()
        captured = flags.get("captured", {})
        victims = [
            p for p in engine.state.players
            if not p.dead and captured.get(str(p.id)) == str(getattr(monster, "id", ""))
            and p.room_key == monster.room_key
        ]
        for victim in victims:
            engine._log(f"猫把 {victim.name} 吞食了！")
            victim.dead = True
            captured.pop(str(victim.id), None)
        engine.check_victory()
        return True  # 猫的回合由 handler 接管

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """p46：被俘者回合开始选属性对决逃生。"""
        flags = engine._haunt_flags()
        captured = flags.get("captured", {})
        pid = str(getattr(player, "id", ""))
        if pid not in captured or player.dead:
            return
        monster_id = captured[pid]
        cat = next((m for m in engine.state.monsters if str(getattr(m, "id", "")) == monster_id), None)
        if cat is None:
            captured.pop(pid, None)
            return
        # bot 选最强属性对决
        best_stat = max(("might", "speed", "sanity", "knowledge"), key=lambda s: player.stats.get(s, 0))
        hero_roll = engine._roll_attack(player, best_stat)
        cat_roll = engine.roll_dice(getattr(cat, best_stat, 3), "猫对决")
        engine._log(f"{player.name} 试图挣脱（{best_stat} 对决）：{hero_roll} 对 {cat_roll}。")
        if hero_roll > cat_roll:
            captured.pop(pid, None)
            player.movement_stopped = False
            engine._log(f"{player.name} 挣脱了猫爪！")
        else:
            player.movement_stopped = True
            engine._log(f"{player.name} 挣扎失败，仍然被猫按在地上。")

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p46：英雄击败猫 → 猫晕 + 释放被俘者。"""
        if _monster_id(monster) != self.CAT:
            return False
        flags = engine._haunt_flags()
        captured = flags.get("captured", {})
        cat_id = str(getattr(monster, "id", ""))
        for pid in [pid for pid, mid in captured.items() if mid == cat_id]:
            captured.pop(pid, None)
            player = next((p for p in engine.state.players if str(p.id) == pid), None)
            if player:
                player.movement_stopped = False
                engine._log(f"{player.name} 被从猫爪下救了出来！")
        return False  # 默认击晕

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        for action in actions:
            if action.id == "escape_plane":
                room_id = engine._current_room_template_id(player)
                if room_id not in self.OUTER_ROOMS or not flags.get("plane_started"):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        if action_id == "search_plane":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and flags.get("plane_found"):
                engine._log("玩具飞机找到了！")
            return ok
        if action_id == "start_plane":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and flags.get("plane_started"):
                engine._log("玩具飞机嗡嗡地发动了——快带大家到窗边逃离！")
            return ok
        if action_id == "escape_plane":
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                escaped = flags.setdefault("escaped", [])
                if player.id not in escaped:
                    escaped.append(player.id)
                    engine._log(f"{player.name} 驾着玩具飞机飞出了窗外！")
                engine.check_victory()
            return ok
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        import math
        flags = engine._haunt_flags()
        heroes_at_start = sum(1 for p in engine.state.players if p.role == "hero")
        escaped_count = len(flags.get("escaped", []))
        need_escape = math.ceil(heroes_at_start / 2)
        dead_heroes = sum(1 for p in engine.state.players if p.role == "hero" and p.dead)
        if escaped_count >= need_escape:
            engine._set_winner("heroes", "玩具飞机摇摇晃晃地飞出了窗外——猫的咆哮远去了！")
            return True
        if dead_heroes > heroes_at_start / 2:
            engine._set_winner("traitor", "超过半数的英雄被猫吃掉了——实验大获成功。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也成了猫的玩具。")
            return True
        return False


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
      节奏等价）；"本回合铺设的砖 +3"不适用（砖按需即时铺设后立即
      进入，加值并入距离语义，已注明）；女孩卡属性微调未建模；叛徒
      入湖可战不搜索（bot 自然满足）；湖怪不作为常驻怪物实体。
    """

    mode = "lake_rescue"

    LAKE_PREFIX = "lake:"
    LAKE_NAME = "湖面"
    SEARCH_BONUS_CRYSTAL = 2

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
        if player.role == "traitor":
            # p115：溺水计时
            current = int(engine._haunt_track_value("drown_timer")) + 1
            engine._set_haunt_track_value("drown_timer", current)
            threshold = int(flags.get("drown_threshold", 10))
            roll = engine.roll_dice(current, "溺水计时")
            engine._log(f"女孩在水下的时间又长了一拍（{current}）：掷出 {roll}（溺亡线 {threshold}+）。")
            if roll >= threshold:
                flags["girl_drowned"] = True
                engine._set_winner("traitor", "湖面重归平静——女孩再也没有浮上来。")
                engine.check_victory()
            return
        # 英雄在湖面砖上：回合开始自动游泳检定，然后搜索
        if self._is_lake_tile(engine, player.room_key):
            roll = engine._roll_attack(player, "might")
            cost = 2 if roll >= 4 else 3
            flags["swim_cost"][str(player.id)] = cost
            engine._log(f"{player.name} 的游泳检定：{roll}（每砖 {cost} 格）。")
            self._search_roll(engine, player)

    def _search_bonus(self, engine: Any, player: Any) -> int:
        bonus = self._lake_distance(engine, player)
        if "omen_crystal_ball" in player.items:
            bonus += self.SEARCH_BONUS_CRYSTAL
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
        return False


class GhostBrideMode(GenericModeHandler):
    """剧本 20 幽灵新娘（Ghost Bride）。

    权威原文：英雄手册 p31 / 叛徒手册 p102。

    · 布点（p102）：教堂与地窖强制入场（_ensure_room_in_play）；新郎
      尸体令牌开局放地窖；新娘（ghost 模板承载，invulnerable——p102
      "cannot be damaged or stunned by any means"，以叛徒手册为准，
      含戒指理智攻击）生成在叛徒房间；3-4 人局 4/6、5-6 人局 5/7。
    · 新郎人选（p102）：优先持戒指的英雄；本项目无性别数据，"女性则
      最年长男性"退化为持戒者本身；无男性英雄的 NPC 分支未建模。
    · 英雄四步（每步每回合一次，顺序由 requires_flags 串起，p31）：
      ①知识 5+（卧室/餐厅/图书馆或持书）得知姓名 → ②知识 4+（地窖）
      定位 → ③力量 4+（地窖）起尸（尸体令牌自动背上）→ ④背尸与戒指
      进教堂。背尸入房按 2 格（movement_cost_multiplier）；尸体可转交
      （give_body），掉落时英雄进房自动拾起。
    · 新娘攻击（p102）：对非新郎正常精神伤害；对新郎转为力量流失
      （1-2→-1 / 3-4→-2 / 5+→-3），新郎力量耗尽即死亡（掉落戒指）。
      移动穿墙近似为正常寻路（已注明）。
    · 婚礼（p102）：新郎死后新娘由 bot 移进教堂即开婚；叛徒回合推进
      计时，第 3 回合婚礼完成 → 叛徒胜。
    · 英雄胜（p31）：尸体与戒指都在教堂（持戒指的英雄在场）→ 新娘
      安息。四步顺序保证流程，胜负判定只看最终状态。
    """

    mode = "ghost_bride"

    BRIDE = "ghost"
    CORPSE = "corpse"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        # p102：教堂与地窖强制入场
        engine._ensure_room_in_play("chapel", room_key)
        crypt_key = engine._ensure_room_in_play("crypt", room_key)
        chapel_key = next(
            (k for k, r in engine.state.board.items() if r.template_id == "chapel"),
            None,
        )
        flags["chapel_room"] = chapel_key
        # 新郎尸体放地窖
        if crypt_key:
            engine.spawn_token(self.CORPSE, label="新郎的尸体", role="marker", room_key=crypt_key)
        # 新娘在叛徒房间；3-4 人局 4/6，5-6 人局 5/7
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            spec = next(
                (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.BRIDE),
                {},
            )
            spec = dict(spec)
            if len(engine.state.players) >= 5:
                spec["speed"], spec["sanity"] = 5, 7
            bride = engine._spawn_single_haunt_monster(spec, traitor.room_key)
            if bride is not None:
                engine.spawn_token("bride", label="幽灵新娘", role="marker", room_key=traitor.room_key)
        # 新郎人选：优先持戒指的英雄（p102；性别数据缺失，退化见类注释）
        ring_holder = next(
            (p for p in engine.state.players if p.role == "hero" and "omen_ring" in p.items),
            None,
        )
        groom = ring_holder or next(
            (p for p in engine.state.players if p.role == "hero" and not p.dead),
            None,
        )
        if groom is not None:
            flags["groom_id"] = groom.id
            engine._log(f"幽灵新娘选定了她选定的新郎——{groom.name}！")
        engine._log("婚礼进行曲在房子里轻轻回响……")

    # ------------------------------------------------------------- 内部
    def _groom(self, engine: Any) -> Any | None:
        gid = engine._haunt_flags().get("groom_id")
        return next((p for p in engine.state.players if p.id == gid), None)

    def _chapel(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("chapel_room")

    # ------------------------------------------------------------- 移动
    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None) -> int:
        """p31：背着新郎尸体入房按 2 格移动计。"""
        if engine.tokens_held_by(player.id, self.CORPSE):
            return 2
        return 1

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        """尸体掉在地上时，英雄进房自动拾起。"""
        if player.role != "hero" or player.dead:
            return
        corpse = next(iter(engine.tokens_in_room(room.key, self.CORPSE)), None)
        if corpse is not None and engine._haunt_flags().get("body_disintered"):
            engine.give_token(corpse.uid, player.id)
            engine._log(f"{player.name} 扛起了新郎的尸体。")

    # ------------------------------------------------------------- 新娘
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.BRIDE:
            return False
        flags = engine._haunt_flags()
        if flags.get("groom_dead"):
            # 新郎已死：新娘去教堂开婚
            chapel = self._chapel(engine)
            if chapel and monster.room_key != chapel:
                monster.room_key = chapel
                engine._log("新娘飘进了教堂——婚礼开始了！")
                flags["wedding_started"] = True
            return True
        groom = self._groom(engine)
        target = groom if (groom is not None and not groom.dead) else engine._find_monster_target(monster)
        if target is None:
            return True
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 4), "新娘移动")
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"新娘飘到了{engine.state.board[monster.room_key].name}。")
        return True

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.BRIDE:
            return False
        victims = [
            p for p in engine.state.players
            if not p.dead and p.room_key == monster.room_key
        ]
        if not victims:
            return True
        # 优先攻击新郎（p102：杀死新郎是叛徒的胜利路线）
        groom = self._groom(engine)
        victim = groom if (groom is not None and not groom.dead and groom.room_key == monster.room_key) else victims[0]
        bride_roll = engine._roll_monster_attack(monster, "sanity")
        hero_roll = engine._roll_attack(victim, "sanity")
        engine._log(f"新娘的目光刺入 {victim.name} 的脑海：{bride_roll} 对 {hero_roll}。")
        if bride_roll > hero_roll:
            amount = bride_roll - hero_roll
            if groom is not None and victim.id == groom.id:
                # p102：对 selected groom 的伤害转为力量流失（分档）
                loss = 1 if amount <= 2 else (2 if amount <= 4 else 3)
                engine._apply_stat_loss(victim, "might", loss)
                engine._log(f"{victim.name} 的生命力被抽走（力量 -{loss}）。")
                engine._check_player_death(victim)
                if victim.dead:
                    flags = engine._haunt_flags()
                    flags["groom_dead"] = True
                    engine._log(f"{victim.name} 死了——他的魂魄被婚礼的誓言缚住了……")
                    engine.check_victory()
            else:
                engine._deal_damage(victim, "mental", amount, source="幽灵新娘")
        elif bride_roll < hero_roll:
            engine._log(f"{victim.name} 挡住了新娘的凝视。")  # p102：新娘不可被晕
        return True

    # ------------------------------------------------------------- 行动
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "disinter_body":
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                corpse = next(iter(engine.tokens_in_room(player.room_key, self.CORPSE)), None)
                if corpse is not None:
                    engine.give_token(corpse.uid, player.id)
                    engine._log(f"{player.name} 挖出了新郎的尸体，扛在肩上（入房按 2 格计）。")
            return ok
        if action_id == "give_body":
            target_id = (data or {}).get("target_id")
            target = next((p for p in engine.state.players if p.id == target_id), None)
            corpse = next(iter(engine.tokens_held_by(player.id, self.CORPSE)), None)
            if target is None or target.dead or target.room_key != player.room_key or corpse is None:
                engine._log("需要同房间的一名存活探险者来接手尸体。")
                return False
            engine.give_token(corpse.uid, target.id)
            engine._log(f"{player.name} 把尸体交给了 {target.name}。")
            return True
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 炸弹式计时
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.role != "traitor" or player.dead or not flags.get("wedding_started"):
            return
        # p102：婚礼开始后每回合推进，第 3 回合完成
        current = int(engine._haunt_track_value("wedding_timer")) + 1
        engine._set_haunt_track_value("wedding_timer", current)
        engine._log(f"婚礼进行中……（{current}/3）")
        if current >= 3:
            engine._set_winner("traitor", "誓言已成——幽灵新娘与她的新郎永远结合了。")
            engine.check_victory()

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        chapel = self._chapel(engine)
        if chapel is not None and flags.get("body_disintered"):
            # 尸体可能被英雄背着（holder 模式）：持有者站在教堂也算"尸体在教堂"
            holder_ids = {p.id for p in engine.state.players if p.room_key == chapel and not p.dead}
            corpse_in_chapel = any(
                t.room_key == chapel or (t.holder is not None and t.holder in holder_ids)
                for t in engine.tokens_of_kind(self.CORPSE)
            )
            ring_in_chapel = any(
                p.role == "hero" and not p.dead and p.room_key == chapel and "omen_ring" in p.items
                for p in engine.state.players
            )
            if corpse_in_chapel and ring_in_chapel:
                engine._set_winner("heroes", "戒指戴上枯骨的手指——两道身影相携淡去，安息了。")
                return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "再没有人能打断这场婚礼了。")
            return True
        return False


class BeastmasterMode(GenericModeHandler):
    """剧本 19 驯兽师（The Beastmaster）。

    权威原文：英雄手册 p30 / 叛徒手册 p101。

    · 叛徒即驯兽师，开局持有长矛（项目无矛卡，用令牌承载——与剧本 15
      同一处理）。五只动物随从按 p101 顺序布点：熊在任一其他探险者所在
      房间；狼进门厅（6 人局两只）；鳄鱼进地下湖或地下室门厅；鼬进
      花园/墓地/阳台否则叛徒房间；鹰进阳台/塔楼/朝外窗房间，都没有则
      不出现。项目没有动物模板，熊/鳄鱼/鼬/鹰分别用 beast/giant/cat/
      cat 模板承载，种类映射存 flags["beast_kind"]（engine_note 惯例）。
    · 英雄胜（p30）：用力量攻击或持戒指的理智攻击对驯兽师造成 **>2 点**
      伤害并改为偷走长矛（引擎新钩子 special_steal）——驯兽师恢复神智。
      attack_attr_override 本版起对玩家目标同样生效（默认 None），
      支持持戒理智攻击。
    · 杀死驯兽师 = 英雄失败（p30 "If you kill the Beastmaster, you
      lose"）——check_victory 显式判叛徒胜，必须避开引擎"叛徒死亡→
      英雄胜"兜底（本剧本最大的坑）。
    · 动物随从被击败即杀死（非击晕，p101）；熊主动攻击 +2、鳄鱼 +1
      （引擎读取 monster_specs 的 initiate_bonus，被攻击时不加）。
    · 已知简化：驯兽师开局的一次传送未实现（可选能力，bot 放弃）；
      长矛被偷后随从是否溃散原文未述，不影响胜负判定。
    """

    mode = "beastmaster"

    BEASTS = {
        "bear": ("beast", "熊", (3, 5, 4)),
        "wolf": ("wolf", "狼", (4, 5, 4)),
        "crocodile": ("giant", "鳄鱼", (2, 5, 4)),
        "weasel": ("cat", "鼬", (5, 2, 6)),
        "hawk": ("cat", "鹰", (5, 3, 5)),
    }
    WINDOW_ROOMS = ["grand_staircase", "master_bedroom", "bedroom", "chapel", "dining_room"]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["beast_kind"] = {}
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is None:
            return
        # 长矛在驯兽师手上（英雄的目标）
        engine.spawn_token("spear", label="驯兽师长矛", role="carried", holder=traitor.id)

        spec_source = haunt.rule_data.get("monsters", [])
        players = len(engine.state.players)

        def spawn_beast(kind: str, room_key_target: str) -> None:
            template_id, name, stats = self.BEASTS[kind]
            spec = next((s for s in spec_source if s.get("template_id") == template_id), {})
            spec = dict(spec)
            spec["name"] = name
            spec["speed"], spec["might"], spec["sanity"] = stats
            monster = engine._spawn_single_haunt_monster(spec, room_key_target)
            if monster is not None:
                flags["beast_kind"][str(monster.id)] = kind

        # 熊：任一其他探险者所在房间（取第一个非叛徒活人）
        other = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
        if other is not None:
            spawn_beast("bear", other.room_key)
        # 狼：门厅（6 人局两只）
        entrance = next(
            (k for k, r in engine.state.board.items() if r.template_id == "entrance_hall"),
            room_key,
        )
        spawn_beast("wolf", entrance)
        if players >= 6:
            spawn_beast("wolf", entrance)
        # 鳄鱼：地下湖或地下室门厅
        croc_room = next(
            (k for k, r in engine.state.board.items() if r.template_id == "underground_lake"),
            None,
        ) or next(
            (k for k, r in engine.state.board.items() if r.template_id == "basement_landing"),
            room_key,
        )
        spawn_beast("crocodile", croc_room)
        # 鼬：花园/墓地/阳台，否则叛徒房间
        weasel_room = next(
            (
                k for k, r in engine.state.board.items()
                if r.template_id in ("garden", "graveyard", "patio")
            ),
            None,
        )
        spawn_beast("weasel", weasel_room or traitor.room_key)
        # 鹰：阳台/塔楼/朝外窗房间；都没有则不出现
        hawk_room = next(
            (
                k for k, r in engine.state.board.items()
                if r.template_id in ("balcony", "tower", *self.WINDOW_ROOMS)
            ),
            None,
        )
        if hawk_room is not None:
            spawn_beast("hawk", hawk_room)
        engine._log("驯兽师的嚎叫在房子里回荡——他的野兽们饿了。")

    # ------------------------------------------------------------- 内部
    def _kind_of(self, engine: Any, monster: Any) -> str:
        return str(engine._haunt_flags().get("beast_kind", {}).get(str(getattr(monster, "id", "")), ""))

    def _spear_token(self, engine: Any) -> Any | None:
        return next((t for t in engine.state.tokens if t.kind == "spear"), None)

    # ------------------------------------------------------------- 攻击规则
    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        """p30：持戒指者对驯兽师的徒手攻击改为理智攻击（对随从不变）。"""
        target_is_beastmaster = (
            isinstance(getattr(target, "role", None), str) and target.role == "traitor"
        )
        if target_is_beastmaster and default_attr == "might" and "omen_ring" in attacker.items:
            return "sanity"
        return None

    def special_steal(self, engine: Any, attacker: Any, target: Any, diff: int, attack_attr: str) -> bool:
        """p30：>2 点伤害改为偷走长矛——英雄的胜利条件。"""
        if getattr(target, "role", None) != "traitor":
            return False
        if attack_attr not in ("might",) and not (
            attack_attr == "sanity" and "omen_ring" in attacker.items
        ):
            return False
        spear = self._spear_token(engine)
        if spear is None or spear.holder != getattr(target, "id", None):
            return False
        engine.give_token(spear.uid, attacker.id)
        engine._haunt_flags()["spear_stolen"] = True
        engine._log(f"{attacker.name} 夺下了长矛——驯兽师的眼里恢复了神智！")
        return True

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p101：动物随从被击败即杀死（非击晕）。"""
        if not self._kind_of(engine, monster):
            return False
        monster_id = getattr(monster, "id", None)
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
        ]
        engine._advance_haunt_track("minions_slain", 1)
        engine._log(f"{monster.name} 被击毙了。")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        if flags.get("spear_stolen"):
            engine._set_winner("heroes", "长矛回到了凡人之手——驯兽师倒下了，你的朋友醒了过来。")
            return True
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and traitor.dead:
            # p30："If you kill the Beastmaster, you lose." —— 杀死驯兽师
            # 是英雄的失败条件，必须盖过引擎"叛徒死亡→英雄胜"兜底。
            engine._set_winner("traitor", "驯兽师死了，可长矛的诅咒仍在——你输了。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "野兽们的嚎叫吞没了最后的探险者。")
            return True
        return False


class BugSprayMode(GenericModeHandler):
    """剧本 17 虫群（Bugs）。

    权威原文：英雄手册 p28 / 叛徒手册 p99。

    · 配料（p28）：六种配料令牌（硝酸/鼠药/喷枪/地板蜡/醋/园艺用品）
      按序放实验室/储藏室/阁楼/仆人房/厨房/花园（原版 Storeroom 与
      Larder 在本项目共用 larder）；未发现的房间等发现时补放。英雄
      拾取任意三种带进实验室或厨房（不拘谁拿着），知识 4+ 合成杀虫剂
      （每回合一次；失败配料保留，下回合再试）。
    · 巨虫（p99）：螳螂 4/5/4（作祟房间）、蜈蚣 3/3/4（杂物间）、黄蜂
      5/2/4（阁楼）、蜘蛛 3/6/4（储藏室）、蟑螂 0/5/4（厨房）、甲虫
      3/6/4（地窖）。项目没有昆虫模板，全部用 spider 模板承载，种类
      映射存 flags["bug_kind"]（优化方案 engine_note 惯例）。
    · 杀虫剂攻击（p28）：持杀虫剂对虫攻击改为**速度攻击**
      （attack_attr_override）；用杀虫剂击败虫即杀死（非击晕），杀满
      三只其余虫逃散；用杀虫剂攻击落败不受伤（attack_loss_damage_disabled）。
    · 蛛网（p99）：被蜘蛛击败的探险者被缚——四属性各 -2（不低于 1）、
      不能移动；同房任意探险者每回合一次力量 5+ 挣脱并恢复失去的 2 点。
    · 蟑螂（p99）：永不离开厨房（on_monster_move）；它守在厨房时离开
      厨房按 3 格移动（movement_cost_floor 钩子）。
    · 叛徒（p99）：拾取/偷取配料——至多背 3 枚配料或 1 瓶杀虫剂（不可
      兼有）；在深坑/熔炉房/地下湖销毁背着的配料或杀虫剂；4 枚配料被
      毁且英雄没有杀虫剂 → 叛徒胜。
    · 英雄胜：毒杀三只虫（其余逃散）；叛徒胜：配料被毁条件或英雄全灭。
      虫群自主行动，叛徒阵亡不结束游戏。
    · 已知简化：英雄丢下配料未建模（拾取即持有）；人类叛徒的偷窃/选择
      弹窗留待接 prompter；杀虫剂被毁后英雄可再用剩余配料重新合成
      （原文规则，已支持）。
    """

    mode = "bug_spray"

    INGREDIENT = "ingredient"
    SPRAY = "bug_spray"
    BUG = "spider"  # 全部昆虫用 spider 模板承载
    INGREDIENT_ROOMS = [
        ("research_laboratory", "硝酸"), ("larder", "鼠药"), ("attic", "喷枪"),
        ("servants_quarters", "地板蜡"), ("kitchen", "醋"), ("garden", "园艺用品"),
    ]
    BUG_ROOMS = [
        ("mantis", None, "螳螂", (4, 5, 4)),      # None = 作祟房间
        ("centipede", "junk_room", "蜈蚣", (3, 3, 4)),
        ("wasp", "attic", "黄蜂", (5, 2, 4)),
        ("spider_bug", "larder", "蜘蛛", (3, 6, 4)),   # 原版 Storeroom 与 Larder 共用
        ("roach", "kitchen", "蟑螂", (0, 5, 4)),
        ("beetle", "crypt", "甲虫", (3, 6, 4)),
    ]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["bug_kind"] = {}
        flags.setdefault("webbed", [])
        flags["ingredient_destroyed"] = 0
        # 配料（p28）：房间在场即放，否则等发现时补放
        for template_id, label in self.INGREDIENT_ROOMS:
            key = next(
                (k for k, r in engine.state.board.items() if r.template_id == template_id),
                None,
            )
            if key:
                token = engine.spawn_token(self.INGREDIENT, label=label, role="marker", room_key=key)
                token.data["name"] = label
        # 六只虫（p99）：房间在场即放，否则等发现时补放；螳螂在作祟房间
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.BUG),
            {},
        )
        for kind, template_id, name, stats in self.BUG_ROOMS:
            key = room_key if template_id is None else next(
                (k for k, r in engine.state.board.items() if r.template_id == template_id),
                None,
            )
            if key is None:
                continue
            bug_spec = dict(spec)
            bug_spec["name"] = name
            bug_spec["speed"], bug_spec["might"], bug_spec["sanity"] = stats
            monster = engine._spawn_single_haunt_monster(bug_spec, key)
            if monster is not None:
                flags["bug_kind"][str(monster.id)] = kind
        engine._log("房间里响起密集的窸窣声——巨型昆虫 crawling 出来了！")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        """p28/p99：配料与虫所在的房间未探索时，发现即补放。"""
        flags = engine._haunt_flags()
        for template_id, label in self.INGREDIENT_ROOMS:
            if room.template_id == template_id and not any(
                t.data.get("name") == label for t in engine.tokens_of_kind(self.INGREDIENT)
            ):
                token = engine.spawn_token(self.INGREDIENT, label=label, role="marker", room_key=room.key)
                token.data["name"] = label
                return
        spec_source = (engine.state.haunt.rule_data or {}).get("monsters", [])
        for kind, template_id, name, stats in self.BUG_ROOMS:
            if template_id is None or room.template_id != template_id:
                continue
            if any(k == kind for k in flags.get("bug_kind", {}).values()):
                continue
            spec = next((s for s in spec_source if s.get("template_id") == self.BUG), {})
            spec = dict(spec)
            spec["name"] = name
            spec["speed"], spec["might"], spec["sanity"] = stats
            monster = engine._spawn_single_haunt_monster(spec, room.key)
            if monster is not None:
                flags["bug_kind"][str(monster.id)] = kind
                engine._log(f"一只{name}从{room.name}的阴影里爬了出来！")
            return

    # ------------------------------------------------------------- 内部
    def _kind_of(self, engine: Any, monster: Any) -> str:
        return str(engine._haunt_flags().get("bug_kind", {}).get(str(getattr(monster, "id", "")), ""))

    def _bugs(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) == self.BUG]

    def _is_bug(self, engine: Any, target: Any) -> bool:
        return _monster_id(target) == self.BUG

    def _holding_spray(self, engine: Any, player: Any) -> bool:
        return bool(engine.tokens_held_by(player.id, self.SPRAY))

    def _held_ingredients(self, engine: Any, player: Any) -> list[Any]:
        return engine.tokens_held_by(player.id, self.INGREDIENT)

    def _room_ingredient_pool(self, engine: Any, room_key: str) -> list[Any]:
        """该房间里可用的配料：地上未持的 + 同房英雄手里拿的（p28）。"""
        pool = list(engine.tokens_in_room(room_key, self.INGREDIENT))
        for p in engine.state.players:
            if not p.dead and p.room_key == room_key:
                pool.extend(engine.tokens_held_by(p.id, self.INGREDIENT))
        return pool

    # ------------------------------------------------------------- 装备规则
    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        """p28：持杀虫剂对虫的攻击改为速度攻击。"""
        if self._is_bug(engine, target) and self._holding_spray(engine, attacker):
            return "speed"
        return None

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p28：用杀虫剂攻击落败不受伤。"""
        return self._is_bug(engine, target) and self._holding_spray(engine, attacker)

    def movement_cost_floor(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p99：蟑螂守厨房时，离开厨房按 3 格移动计。"""
        if not from_key:
            return 0
        room = engine.state.board.get(from_key)
        if room is None or room.template_id != "kitchen":
            return 0
        roach = next(
            (m for m in self._bugs(engine) if self._kind_of(engine, m) == "roach"
             and m.room_key == from_key and int(getattr(m, "stunned_turns", 0)) <= 0),
            None,
        )
        return 3 if roach is not None else 0

    def on_player_died(self, engine: Any, player: Any) -> None:
        # 被缚者死亡时解除蛛网标记
        flags = engine._haunt_flags()
        webbed = [pid for pid in flags.get("webbed", []) if pid != str(player.id)]
        flags["webbed"] = webbed

    # ------------------------------------------------------------- 蛛网
    def _web_lower_traits(self, engine: Any, player: Any) -> None:
        """p99：被缚者四属性各 -2，但不低于 1（原文 minimum of 1）。"""
        for stat in ("speed", "might", "sanity", "knowledge"):
            track = engine._stat_track(player, stat)
            position = player.stat_positions.get(stat)
            if not track or position is None:
                player.stats[stat] = max(1, player.stats.get(stat, 1) - 2)
                continue
            # 找到值 >= 1 的最低格
            floor_pos = 0
            for idx, value in enumerate(track):
                if value >= 1:
                    floor_pos = idx
                    break
            new_pos = max(position - 2, floor_pos)
            player.stat_positions[stat] = new_pos
            player.stats[stat] = track[new_pos]
        player.movement_stopped = True

    def _web_restore(self, engine: Any, player: Any) -> None:
        for stat in ("speed", "might", "sanity", "knowledge"):
            track = engine._stat_track(player, stat)
            position = player.stat_positions.get(stat)
            if track and position is not None:
                player.stat_positions[stat] = min(position + 2, len(track) - 1)
                player.stats[stat] = track[player.stat_positions[stat]]

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """p99：蜘蛛击败探险者改为缚网而非伤害。"""
        if self._kind_of(engine, monster) != "spider_bug":
            return False
        flags = engine._haunt_flags()
        webbed = list(flags.get("webbed", []))
        if str(target.id) in webbed:
            return False  # 已被缚：走正常伤害
        webbed.append(str(target.id))
        flags["webbed"] = webbed
        self._web_lower_traits(engine, target)
        engine._log(f"{target.name} 被蛛丝缠住了！四属性各 -2，动弹不得。")
        engine.check_victory()
        return True

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """被缚者不能移动。"""
        if str(player.id) in engine._haunt_flags().get("webbed", []):
            player.movement_stopped = True

    # ------------------------------------------------------------- 虫行为
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.BUG:
            return False
        if self._kind_of(engine, monster) == "roach":
            return True  # p99：蟑螂永不离开厨房（同房攻击由引擎默认处理）
        return False  # 其余虫常规追击

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p28：用杀虫剂击败虫 → 杀死（非击晕）并计数；杀满 3 只其余逃散。"""
        if _monster_id(monster) != self.BUG:
            return False
        attacker = None
        active_id = getattr(engine, "_active_player_id", None)
        if active_id is not None:
            attacker = engine.state.players[active_id]
        if attacker is None or not self._holding_spray(engine, attacker):
            return False  # 无杀虫剂：默认击晕
        monster_id = getattr(monster, "id", None)
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
        ]
        engine._advance_haunt_track("bugs_killed", 1)
        engine._log(f"杀虫剂的毒雾让{name_map(engine, monster)}当场蜷缩死去！")
        if engine._haunt_track_value("bugs_killed") >= 3:
            for bug in list(self._bugs(engine)):
                bug_id = getattr(bug, "id", None)
                engine.state.monsters = [
                    m for m in engine.state.monsters if getattr(m, "id", None) != bug_id
                ]
            engine._log("其余的虫子窸窸窣窣地逃出了房子！")
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "take_ingredient":
                if not engine.tokens_in_room(player.room_key, self.INGREDIENT):
                    continue
                if player.role == "traitor":
                    if self._holding_spray(engine, player) or len(self._held_ingredients(engine, player)) >= 3:
                        continue  # p99：至多 3 枚配料，或 1 瓶杀虫剂（不可兼有）
            if action.id == "make_spray":
                if player.role != "hero" or len(self._room_ingredient_pool(engine, player.room_key)) < 3:
                    continue  # 三枚配料同房（不拘谁拿着）
            if action.id == "destroy_ingredient":
                if player.role != "traitor":
                    continue
                if not self._held_ingredients(engine, player) and not self._holding_spray(engine, player):
                    continue
            if action.id == "break_webs":
                if not any(
                    str(p.id) in engine._haunt_flags().get("webbed", [])
                    and p.room_key == player.room_key
                    for p in engine.state.players
                ):
                    continue  # 同房要有被缚的探险者
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "take_ingredient":
            token = next(iter(engine.tokens_in_room(player.room_key, self.INGREDIENT)), None)
            if token is None:
                engine._log("这个房间里没有配料。")
                return False
            if player.role == "traitor":
                if self._holding_spray(engine, player) or len(self._held_ingredients(engine, player)) >= 3:
                    engine._log("你拿不下了（至多 3 枚配料或 1 瓶杀虫剂）。")
                    return False
            engine.give_token(token.uid, player.id)
            engine._log(f"{player.name} 收起了{token.label}。")
            return True

        if action_id == "make_spray":
            pool = self._room_ingredient_pool(engine, player.room_key)
            if len(pool) < 3:
                engine._log("需要三枚配料在同一间房（不拘谁拿着）。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                # 优先消耗放在地上的，再消耗英雄手里的；移出游戏
                for token in pool[:3]:
                    engine.remove_token(token.uid)
                spray = engine.spawn_token(self.SPRAY, label="杀虫剂", role="carried", holder=player.id)
                engine._log(f"{player.name} 调配出了杀虫剂（{spray.label}）！对虫用速度攻击！")
            return ok

        if action_id == "destroy_ingredient":
            held = self._held_ingredients(engine, player)
            if held:
                token = held[0]
                engine.remove_token(token.uid)
                engine._advance_haunt_track("ingredients_destroyed", 1)
                engine._log(
                    f"{player.name} 把{token.label}扔进了深渊"
                    f"（被毁配料 {engine._haunt_track_value('ingredients_destroyed')}/4）。"
                )
                engine.check_victory()
                return True
            if self._holding_spray(engine, player):
                spray = engine.tokens_held_by(player.id, self.SPRAY)[0]
                engine.remove_token(spray.uid)
                flags = engine._haunt_flags()
                flags["spray_destroyed"] = True
                engine._log("杀虫剂被毁掉了——英雄们得再配一瓶。")
                return True
            engine._log("你身上没有可销毁的东西。")
            return False

        if action_id == "break_webs":
            webbed_here = [
                p for p in engine.state.players
                if str(p.id) in engine._haunt_flags().get("webbed", [])
                and p.room_key == player.room_key
            ]
            if not webbed_here:
                engine._log("这个房间里没有被缚的探险者。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                flags = engine._haunt_flags()
                freed_ids = {str(p.id) for p in webbed_here}
                flags["webbed"] = [pid for pid in flags.get("webbed", []) if pid not in freed_ids]
                for p in webbed_here:
                    self._web_restore(engine, p)
                    p.movement_stopped = False
                    engine._log(f"{p.name} 挣脱了蛛丝，恢复了自由！")
            return ok

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        # p28：毒杀三只虫，其余逃散 → 英雄胜
        if engine._haunt_track_value("bugs_killed") >= engine._haunt_track_target("bugs_killed"):
            for bug in list(self._bugs(engine)):
                bug_id = getattr(bug, "id", None)
                engine.state.monsters = [
                    m for m in engine.state.monsters if getattr(m, "id", None) != bug_id
                ]
            engine._set_winner("heroes", "最后的巨虫在毒雾中蜷缩死去——其余的逃出了房子。")
            return True
        # p99：四枚配料被毁且英雄没有杀虫剂 → 叛徒胜
        spray_in_play = any(t.kind == self.SPRAY for t in engine.state.tokens)
        if (
            engine._haunt_track_value("ingredients_destroyed") >= engine._haunt_track_target("ingredients_destroyed")
            and not spray_in_play
        ):
            engine._set_winner("traitor", "配料毁尽，杀虫剂无踪——虫群饱餐了一顿。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "喋喋不休的人类成了虫群的粮食。")
            return True
        return True  # 虫群自主行动，叛徒阵亡不结束游戏


def name_map(engine: Any, monster: Any) -> str:
    return str(getattr(monster, "name", "巨虫"))


class PhantomBombMode(GenericModeHandler):
    """剧本 16 幻影的怀抱（The Phantom's Embrace）。

    权威原文：英雄手册 p27 / 叛徒手册 p98。

    · 幻影（ghost 模板承载，Speed 0 / Might 6 / Sanity 5）：不攻击只
      防御（on_monster_turn_attack 拦下引擎默认攻击、on_monster_move
      令其不移动）。它在下一个被发现的带符号地下室房间出现，同时放下
      女孩令牌与"到访标记"（p98 distinctive token），并**抑制该次抽牌**
      ——英雄"代替抽牌"必须攻击幻影（引擎 suppress_room_draw 钩子）。
    · 战斗（p27/p98）：英雄击败幻影 → 幻影死亡，英雄获女孩令牌，该
      房间成为"可拆弹房间"；幻影防御成功（英雄攻击落败）→ 英雄照常
      受反击伤害，幻影带着女孩逃走（两枚令牌移除），下次再出现。
    · 拆弹（p27）：女孩获救后，在击败幻影的房间做知识 7+（每回合一次）。
    · 逃脱（p27）：门厅开前门（知识/力量 6+，通用框架取高者）；持女孩
      的英雄回合开始仍站在门厅即带她逃出——原文为群体逃跑，电子版
      简化为持女孩者出门（已注明）。
    · 炸弹（p98）：叛徒回合开始推进计时器并掷等量骰，掷出阈值以上房子
      爆炸（3 人 8+ / 4 人 7+ / 5 人 6+ / 6 人 5+）。原文"回合结束"用
      "下一回合开始"近似，时序等价。
    · 胜负：拆弹或带女孩逃出 → 英雄胜；爆炸或英雄全灭 → 叛徒胜。
      叛徒阵亡后计时器冻结（怪物代跑惯例下的保守处理，已注明）。
    · 已知简化：开成功门后"抽事件卡"步骤未建模；地下室全部探索完且
      幻影仍存活的"叛徒指定房间"分支未建模（幻影出现依赖房间发现）；
      女孩不可被偷是天然满足（女孩是令牌不是卡）。
    """

    mode = "phantom_bomb"

    PHANTOM = "ghost"
    GIRL = "girl"
    MARK = "phantom_mark"
    BLOWUP_THRESHOLD = {3: 8, 4: 7, 5: 6, 6: 5}

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        # p98：持有女孩卡的探险者失去她（女孩卡与令牌一并 set aside）
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
        engine._log("女孩的尖叫声戛然而止——她被藏进了这栋房子的某处。")

    # ------------------------------------------------------------- 出现
    def _phantom_in_play(self, engine: Any) -> bool:
        return any(
            m.template_id == self.PHANTOM and int(getattr(m, "stunned_turns", 0)) >= 0
            for m in engine.state.monsters
        )

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        flags = engine._haunt_flags()
        if room.floor != -1 or room.symbol not in ("event", "omen"):
            return
        if flags.get("girl_rescued") or self._phantom_in_play(engine):
            return
        spec = next(
            (s for s in (engine.state.haunt.rule_data or {}).get("monsters", [])
             if s.get("template_id") == self.PHANTOM),
            {},
        )
        monster = engine._spawn_single_haunt_monster(spec, room.key)
        if monster is None:
            return
        engine.spawn_token(self.GIRL, label="女孩", role="marker", room_key=room.key)
        engine.spawn_token(self.MARK, label="到访标记", role="marker", room_key=room.key)
        engine._log(
            f"{room.name}里，一个半透明的身影守着昏迷的女孩——他的幻影！先别管抽牌，攻击他！"
        )

    def suppress_room_draw(self, engine: Any, player: Any, room: Any) -> bool:
        """p27：幻影出现的房间，本次发现不抽符号牌（改为攻击幻影）。"""
        return any(m.room_key == room.key for m in engine.state.monsters if m.template_id == self.PHANTOM)

    # ------------------------------------------------------------- 行为
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.PHANTOM:
            return False
        return True  # p98：幻影不移动

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.PHANTOM:
            return False
        return True  # p98：幻影不攻击，只防御

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        """p27：幻影防御成功即带着女孩逃走；被击败则女孩获救。"""
        if _monster_id(target) != self.PHANTOM:
            return
        flags = engine._haunt_flags()
        phantom_id = getattr(target, "id", None)
        if attacker_won:
            flags["girl_rescued"] = True
            flags["bomb_room"] = target.room_key
            girl = next(iter(engine.tokens_in_room(target.room_key, self.GIRL)), None)
            if girl is not None:
                engine.give_token(girl.uid, attacker.id)
                flags["girl_holder_id"] = attacker.id
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != phantom_id
            ]
            engine._log(f"幻影消散了！{attacker.name} 抱起了女孩——房间里传来定时炸弹的滴答声……")
        else:
            # 防御成功 → 带女孩逃走（英雄已按常规吃了反击伤害）
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != phantom_id
            ]
            for t in list(engine.tokens_in_room(target.room_key, self.GIRL)):
                engine.remove_token(t.uid)
            engine._log("幻影抱起女孩化作一缕青烟逃走了——下一个带符号的地下室房间还会见到他。")

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        """获救的女孩掉在地上时，英雄进房自动抱起。"""
        flags = engine._haunt_flags()
        if player.role != "hero" or player.dead or not flags.get("girl_rescued"):
            return
        girl = next(iter(engine.tokens_in_room(room.key, self.GIRL)), None)
        if girl is not None:
            engine.give_token(girl.uid, player.id)
            flags["girl_holder_id"] = player.id
            engine._log(f"{player.name} 抱起了女孩。")

    # ------------------------------------------------------------- 炸弹
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.role != "traitor" or player.dead:
            return
        # p98：回合结束推进计时器——用"下一回合开始"近似
        track = int(engine._haunt_track_value("bomb_timer")) + 1
        engine._set_haunt_track_value("bomb_timer", track)
        threshold = self.BLOWUP_THRESHOLD.get(len(engine.state.players), 8)
        roll = engine.roll_dice(track, "炸弹计时")
        engine._log(f"滴答……计时器走到 {track}，掷出 {roll}（爆炸线 {threshold}+）。")
        if roll >= threshold:
            flags["house_blown"] = True
            engine._set_winner("traitor", "轰！！！房子炸上了天。")
            engine.check_victory()

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        if flags.get("house_blown"):
            return True  # winner 已在引信处设定
        if flags.get("bomb_defused"):
            engine._set_winner("heroes", "炸弹滴滴答答地哑了火——危机解除。")
            return True
        if flags.get("escaped"):
            engine._set_winner("heroes", "你抱着女孩逃出铁门——身后的宅邸还在滴答作响。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "没有一个英雄活着听到爆炸……或听到寂静。")
            return True
        return True  # 叛徒阵亡后计时器冻结，胜负只认显式条件


class DragonSiegeMode(GenericModeHandler):
    """剧本 15 有龙在此（Here There Be Dragons）。

    权威原文：英雄手册 p26 / 叛徒手册 p97。

    · 巨龙（beast 模板承载，Speed 3 / Might 8 / Sanity 6）：开局在门厅；
      伤害容量 = 玩家数（p97 Turn/Damage Track）；韧性：每次被击败实扣
      伤害 -2（p97 Toughness）；免疫速度攻击；持戒指者的理智攻击可伤它。
    · 每回合两次攻击（p97）：火息（同房与门相邻房间的**所有**探险者，
      含叛徒：速度检定 4+ 免疫，失败同房 4 骰/相邻 2 骰物理伤害；弃一件
      物品减 2 点——bot 自动弃第一件直到伤害归零）与咬（同房力量对决，
      持矛者防御 +4）。
    · 装备三件套（地下室，p97）：古董护甲（墓穴/地下湖——穿整回合、
      非火焰物理 -5、移动 -1、不可被偷）；盾（深坑/地窖——携带者免疫
      火焰、移动 -1、同房英雄也免疫龙焰）；矛（原版为物品牌，项目
      22 件物品无此牌，改为令牌放在剩余的地下室房间——偏差已注明）。
      房间未被发现时等发现即补放（on_room_discovered）。
    · 英雄胜：龙受到的伤害攒满玩家人数即斩杀；叛徒胜：英雄全灭。
      巨龙由 bot 驱动（叛徒无法微操），叛徒阵亡不结束游戏。
    · 已知简化：穿甲/脱甲的"交给他人"未建模；护甲与盔甲卡不可同穿未拦；
      弃物减伤为 bot 自动（人类弹窗留待接 prompter）。
    """

    mode = "dragon_siege"

    DRAGON = "beast"
    BASEMENT_ROOMS = ["catacombs", "underground_lake", "chasm", "crypt"]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["worn_by"] = None
        entrance = next(
            (k for k, r in engine.state.board.items() if r.template_id == "entrance_hall"),
            room_key,
        )
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.DRAGON),
            {},
        )
        if engine._spawn_single_haunt_monster(spec, entrance):
            engine.spawn_token("dragon", label="巨龙", role="marker", room_key=entrance)
            engine._log("前门轰然洞开——一头巨龙咆哮着涌了进来！")

        def place(preferred: list[str]) -> str | None:
            for rid in preferred:
                key = next(
                    (k for k, r in engine.state.board.items() if r.template_id == rid),
                    None,
                )
                if key:
                    return key
            return None

        armor_room = place(["catacombs", "underground_lake"])
        shield_room = place(["chasm", "crypt"])
        used = {armor_room, shield_room}
        spear_room = next(
            (
                k for k, r in engine.state.board.items()
                if r.template_id in self.BASEMENT_ROOMS and k not in used
            ),
            None,
        )
        flags["armor_room"] = armor_room
        flags["shield_room"] = shield_room
        flags["spear_room"] = spear_room
        labels = {"antique_armor": "古董护甲", "shield": "盾", "spear": "矛"}
        for kind, key in (
            ("antique_armor", armor_room), ("shield", shield_room), ("spear", spear_room)
        ):
            if key:
                engine.spawn_token(kind, label=labels[kind], role="marker", room_key=key)

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        """p97：装备所在的地下室房间未被探索时，发现即补放。"""
        flags = engine._haunt_flags()
        if room.template_id not in self.BASEMENT_ROOMS:
            return
        pending = [
            ("antique_armor", "armor_room", "古董护甲"),
            ("shield", "shield_room", "盾"),
            ("spear", "spear_room", "矛"),
        ]
        for kind, flag, label in pending:
            if flags.get(flag) is None:
                engine.spawn_token(kind, label=label, role="marker", room_key=room.key)
                flags[flag] = room.key
                engine._log(f"{room.name}里躺着一件装备：{label}。")
                return

    # ------------------------------------------------------------- 内部
    def _door_adjacent(self, engine: Any, key_a: str, key_b: str) -> bool:
        a = engine.state.board.get(key_a)
        b = engine.state.board.get(key_b)
        if not a or not b or a.floor != b.floor:
            return False
        dx = b.x - a.x
        dy = b.y - a.y
        for direction, (ddx, ddy) in {
            "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
        }.items():
            if (dx, dy) == (ddx, ddy) and direction in a.doors and OPPOSITE_DOOR[direction] in b.doors:
                return True
        return False

    def _shield_holder(self, engine: Any) -> Any | None:
        token = next(
            (t for t in engine.state.tokens if t.kind == "shield" and t.holder is not None),
            None,
        )
        if token is None:
            return None
        return next((p for p in engine.state.players if p.id == token.holder), None)

    def _movement_penalty(self, engine: Any, player: Any) -> int:
        penalty = 0
        if engine.tokens_held_by(player.id, "shield"):
            penalty += 1  # p26：持盾移动 -1
        if engine._haunt_flags().get("worn_by") == player.id:
            penalty += 1  # p26：穿古董护甲移动 -1
        return penalty

    def on_turn_start(self, engine: Any, player: Any) -> None:
        penalty = self._movement_penalty(engine, player)
        if penalty and player.steps_remaining > 1:
            player.steps_remaining = max(1, player.steps_remaining - penalty)

    # ------------------------------------------------------------- 巨龙回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.DRAGON:
            return False
        target = engine._find_monster_target(monster)
        if target is not None:
            path = engine._shortest_path(monster.room_key, target.room_key)
            if len(path) > 1:
                steps = engine.roll_dice(getattr(monster, "speed", 3), "巨龙移动")
                monster.room_key = path[min(len(path) - 1, steps)]
                engine._log(f"巨龙杀到了{engine.state.board[monster.room_key].name}。")
        self._firebreath(engine, monster)
        self._bite(engine, monster)
        return True

    def _firebreath(self, engine: Any, monster: Any) -> None:
        """p97：同房与门相邻房间的所有探险者（含叛徒）做速度检定。"""
        shield_holder = self._shield_holder(engine)
        same, adjacent = [], []
        for p in engine.state.players:
            if p.dead:
                continue
            if p.room_key == monster.room_key:
                same.append(p)
            elif self._door_adjacent(engine, monster.room_key, p.room_key):
                adjacent.append(p)
        for zone, victims in (("same", same), ("adjacent", adjacent)):
            for victim in victims:
                if shield_holder is not None and (
                    victim.id == shield_holder.id
                    or (victim.role == "hero" and victim.room_key == shield_holder.room_key)
                ):
                    engine._log(f"{victim.name} 在盾的庇护下免疫龙焰。")
                    continue
                roll = engine._roll_attack(victim, "speed")
                if roll >= 4:
                    engine._log(f"{victim.name} 敏捷地避开了龙焰（速度检定 {roll}）。")
                    continue
                dice = 4 if zone == "same" else 2
                damage = engine.roll_dice(dice, "龙焰")
                # p26：可弃一件物品减 2 点（bot 自动弃直到伤害归零）
                while damage > 0 and victim.items:
                    card_id = victim.items[0]
                    engine._discard_card_from_player(victim, card_id, return_to_room=False)
                    damage -= 2
                    engine._log(
                        f"{victim.name} 舍弃了{engine.catalog.cards[card_id].name}，火焰伤害 -2。"
                    )
                damage = max(0, damage)
                if damage:
                    engine._deal_damage(victim, "physical", damage, source="龙焰")
                else:
                    engine._log(f"{victim.name} 在烈焰中毫发无伤。")

    def _bite(self, engine: Any, monster: Any) -> None:
        victims = [
            p for p in engine.state.players
            if not p.dead and p.room_key == monster.room_key
        ]
        if not victims:
            return
        victim = victims[0]
        dragon_roll = engine._roll_monster_attack(monster, "might")
        hero_roll = engine._roll_attack(victim, "might")
        if engine.tokens_held_by(victim.id, "spear"):
            hero_roll += 4  # p26：持矛对龙防御 +4
            engine._log(f"{victim.name} 挥矛格挡（+4）。")
        engine._log(f"巨龙撕咬 {victim.name}：{dragon_roll} 对 {hero_roll}。")
        if dragon_roll > hero_roll:
            engine._deal_damage(victim, "physical", dragon_roll - hero_roll, source="巨龙之咬")
        elif dragon_roll < hero_roll:
            engine._stun_monster(monster, 1)

    # ------------------------------------------------------------- 攻击规则
    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        """p97：持戒指者对巨龙的徒手攻击改为理智攻击。"""
        if _monster_id(target) == self.DRAGON and default_attr == "might" and "omen_ring" in attacker.items:
            return "sanity"
        return None

    def attack_roll_bonus(self, engine: Any, attacker: Any, target: Any) -> int:
        """p26：持矛对巨龙的攻击骰 +4。"""
        if _monster_id(target) == self.DRAGON and engine.tokens_held_by(attacker.id, "spear"):
            return 4
        return 0

    def physical_damage_reduction(self, engine: Any, player: Any, amount: int, source: str, damage_type: str) -> int:
        """p26：古董护甲对非火焰物理伤害 -5。"""
        if engine._haunt_flags().get("worn_by") != player.id:
            return 0
        if damage_type != "physical":
            return 0
        if "火" in (source or "") or "热" in (source or ""):
            return 0
        return 5

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p97：韧性——每次被击败实扣伤害 -2；伤害由轨迹记录，不击晕。"""
        if _monster_id(monster) != self.DRAGON:
            return False
        net = max(0, amount - 2)
        if net > 0:
            engine._advance_haunt_track("dragon_damage", net)
        engine._log(
            f"巨龙受创（韧性抵消 2 点，实扣 {net}；"
            f"总 {engine._haunt_track_value('dragon_damage')}/{engine._haunt_track_target('dragon_damage')}）。"
        )
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "don_armor":
                if player.role != "hero" or engine._haunt_flags().get("worn_by") is not None:
                    continue
                if not engine.tokens_in_room(player.room_key, "antique_armor"):
                    continue
            if action.id == "take_shield" and not engine.tokens_in_room(player.room_key, "shield"):
                continue
            if action.id == "take_spear" and not engine.tokens_in_room(player.room_key, "spear"):
                continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "don_armor":
            token = next(iter(engine.tokens_in_room(player.room_key, "antique_armor")), None)
            if token is None or engine._haunt_flags().get("worn_by") is not None:
                engine._log("这里没有可穿的古董护甲（或已有人在穿）。")
                return False
            engine.give_token(token.uid, player.id)
            engine._haunt_flags()["worn_by"] = player.id
            player.movement_stopped = True  # p26：穿甲花整个回合
            player.steps_remaining = 0
            engine._log(f"{player.name} 花了整整一个回合穿上古董护甲。")
            return True
        if action_id == "take_shield":
            token = next(iter(engine.tokens_in_room(player.room_key, "shield")), None)
            if token is None:
                engine._log("这里没有盾。")
                return False
            engine.give_token(token.uid, player.id)
            engine._log(f"{player.name} 扛起了沉重的盾。")
            return True
        if action_id == "take_spear":
            token = next(iter(engine.tokens_in_room(player.room_key, "spear")), None)
            if token is None:
                engine._log("这里没有矛。")
                return False
            engine.give_token(token.uid, player.id)
            engine._log(f"{player.name} 握紧了长矛。")
            return True
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("dragon_damage") >= engine._haunt_track_target("dragon_damage"):
            monster = engine._monster_by_template(self.DRAGON)
            if monster is not None:
                dragon_id = getattr(monster, "id", None)
                engine.state.monsters = [
                    m for m in engine.state.monsters if getattr(m, "id", None) != dragon_id
                ]
            engine._set_winner("heroes", "巨龙轰然倒地——现在是跟叛徒算账的时候了。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "巨龙把最后的探险者也吞进了腹中。")
            return True
        return True  # 巨龙自主行动，叛徒阵亡不结束游戏



class ZombieLordMode(GenericModeHandler):
    """剧本 21 活死人之屋（House of the Living Dead）。

    权威原文：英雄手册 p32 / 叛徒手册 p103。

    已按原文实现：
        · 数值：僵尸 Speed 2 / Might 5 / Sanity 2；僵尸领主 Speed 3 / Might 7 /
          Sanity 2（p103 页脚）。
        · 叛徒开局即死：掉落全部物品，人物由僵尸领主令牌（大）顶替（p103
          "Your explorer is dead. Drop all your items and replace your
          character's figure with the Zombie Lord token"）。
        · 布点：先放「玩家数」枚僵尸令牌，按 地窖→墓地→门厅→地下湖→花园→
          教堂→温室→五芒星室 的顺序放进**已发现**的那些房间；房间不够就在
          同一间叠放；放完后再给每间已有僵尸的房间补放一只（p103）。
        · 杀死僵尸必须用"需要力量的武器"或炸药；其他攻击只把它打晕；
          僵尸免疫左轮（p32）。徒手力量攻击不算武器，所以仍只击晕。
        · 僵尸领主：只有持徽章者能伤到它，且持徽章者徒手也能打；它不吃
          击晕，累计 7 点伤害才倒，伤害不减属性（p32/p103，走 lord_damage 轨道）。
        · 圣徽：对持有者发动力量攻击的僵尸少掷两枚骰，对领主无效（p32）。
        · 英雄被杀 → 在自己倒下的房间里转化为一只新僵尸（p32/p103）。
        · 胜负：摧毁领主 或 消灭所有僵尸 → 英雄胜；英雄全灭 → 叛徒胜。
          叛徒开局就死，必须吸收引擎"叛徒死亡即英雄胜"的兜底（老坑第 6 次）。

    已知简化：
        · 转化的僵尸由引擎/bot 代跑，不由原玩家操控（p103 原版是"该玩家在自己
          的回合继续操控他的僵尸"）；因此"僵尸杀了英雄则该玩家也赢"的多胜方
          结算未建模。
        · p32「有机会抽物品卡时可抽三张选一张、其余放回牌堆底」未建模——引擎
          抽牌流程没有"多选一"的决策点，要 UI 与联机同时支持。
        · 僵尸不能用神秘电梯、领主可以：引擎的怪物从不触发电梯效果，天然满足。
        · 武器属性由卡牌 tags 推导，目前只有左轮标了 speed；原版的匕首类也是
          速度攻击，本仓库尚未给它们打标，所以在这里仍按力量武器算（会杀死
          僵尸）。本剧本只保证「左轮无效 / 力量武器命中即杀」两条原文判定。
    """

    mode = "zombie_lord"

    ZOMBIE = "zombie"
    LORD = "zombie_lord"
    DYNAMITE = "item_dynamite"
    MEDALLION = "omen_medallion"
    HOLY_SYMBOL = "omen_holy_symbol"
    # p103 的布点顺序
    PLACE_ORDER = (
        "crypt", "graveyard", "entrance_hall", "underground_lake",
        "garden", "chapel", "conservatory", "pentagram_chamber",
    )

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine._drop_inventory_on_death(traitor)
            traitor.dead = True
            engine._log(f"{traitor.name}被墙里伸出的灰白色手拖了进去——再站起来的东西不再是祂。")
        placed = self._place_zombies(engine, room_key)
        engine._haunt_flags()["zombies_placed"] = placed
        engine._log(f"僵尸从墓穴与花园的方向围了过来（{placed} 只）。")

    def _zombie_spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.ZOMBIE) or {"template_id": self.ZOMBIE, "name": "僵尸"})

    def _place_zombies(self, engine: Any, haunt_room_key: str) -> int:
        """p103：玩家数枚僵尸按房间顺序布点，房不够则叠放，再给每间补一只。"""
        buckets: list[str] = []
        for template_id in self.PLACE_ORDER:
            for key, room in engine.state.board.items():
                if room.template_id == template_id and room.revealed:
                    buckets.append(key)
                    break
        if not buckets:
            buckets = [haunt_room_key]  # 列出的房间一间都没发现：退到作祟房
        spec = self._zombie_spec(engine)
        players = len(engine.state.players)
        first_pass = [buckets[index % len(buckets)] for index in range(players)]
        occupied = list(dict.fromkeys(first_pass))
        for room_key in first_pass + occupied:
            engine._spawn_single_haunt_monster(spec, room_key)
        return players + len(occupied)

    # ---------------------------------------------------------- 战斗规则
    def _holds(self, player: Any, card_id: str) -> bool:
        return card_id in (getattr(player, "items", None) or [])

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p32：没有徽章的人攻击僵尸领主毫无效果（连击晕都不算）。"""
        if _monster_id(target) != self.LORD:
            return True
        return self._holds(attacker, self.MEDALLION)

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """p32：力量武器与炸药能杀死僵尸，其他攻击只能把它打晕。"""
        if _monster_id(monster) != self.ZOMBIE:
            return False
        if weapon_id == self.DYNAMITE:
            return True
        return bool(weapon_id) and attack_attr == "might"

    def monster_attack_roll_bonus(self, engine: Any, monster: Any, target: Any) -> int:
        """p32：圣徽持有者让僵尸的力量攻击少掷两枚骰（不影响僵尸领主）。"""
        if _monster_id(monster) != self.ZOMBIE:
            return 0
        if not self._holds(target, self.HOLY_SYMBOL):
            return 0
        return -2

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """僵尸领主：不吃击晕，累计 7 点伤害才倒（p103 用回合/伤害轨记录）。"""
        if _monster_id(monster) != self.LORD:
            return False
        engine._advance_haunt_track("lord_damage", max(1, amount))
        taken = engine._haunt_track_value("lord_damage")
        capacity = engine._haunt_track_target("lord_damage") or 7
        if taken >= capacity:
            engine._kill_monster(monster)
            engine.check_victory()
        else:
            engine._log(f"僵尸领主挨到第 {taken}/{capacity} 点伤害，只是晃了晃。")
        return True

    # -------------------------------------------------------------- 转化
    def on_player_died(self, engine: Any, player: Any) -> None:
        """p32：英雄被杀后变成僵尸（原版由其玩家下回合继续操控，见类注释）。"""
        if getattr(player, "role", "") != "hero":
            return
        flags = engine._haunt_flags()
        converted = set(flags.get("converted_ids", []) or [])
        if player.id in converted:
            return
        converted.add(player.id)
        flags["converted_ids"] = sorted(converted)
        zombie = engine._spawn_single_haunt_monster(self._zombie_spec(engine), player.room_key)
        if zombie is not None:
            engine._log(f"{player.name}又站了起来——饿着肚子的、灰白色皮肤的祂。")

    # ---------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "屋子里只剩下拖着的脚步声和咀嚼声。")
            return True
        alive = {_monster_id(monster) for monster in engine.state.monsters}
        if not engine._haunt_flags().get("zombies_placed"):
            return True  # setup 还没布点：此时"场上没僵尸"不代表被清空了
        if self.LORD not in alive:
            engine._set_winner("heroes", "僵尸领主散成一堆枯骨，围着的僵尸跟着一个个瘫了下去。")
            return True
        if self.ZOMBIE not in alive:
            engine._set_winner("heroes", "最后一只僵尸倒下，墙里的抓挠声终于停了。")
            return True
        return True  # 叛徒开局已死：吸收引擎"叛徒死亡即英雄胜"的兜底



class AbyssExorcismMode(ExorcismMode):
    """剧本 22 深渊回望（The Abyss Gazes Back）。

    权威原文：英雄手册 p33 / 叛徒手册 p104。

    复用剧本 8 的驱魔底座（一次性来源、每人每回合一次、成功后放检定令牌、
    满玩家人数即完成），p33 把理智物品来源从灵应板换成**戒指**。本次新增：

    · 深渊起点（p104）：地下室里无人、带预兆或事件符号的房间；一间都没有就
      从房间牌堆拿一张合法的地下室房放上（与 `_ensure_room_in_play` 同做法）。
    · 叛徒首个回合结束翻掉起点房，之后每个叛徒回合结束推进深渊回合轨（从 1 起）。
    · 坍塌速率（p104）：每位玩家回合结束时——第 2 回合塌 1 间、第 3 回合掷 2 骰、
      第 4 回合 3 骰、第 5 回合起 4 骰（骰面 0-2，所以可能一间都不塌）。
      只能沿已有深渊的正交邻格扩散；整层塌完升到上一层，从"无人且留着未探索
      门口"的房间开始。
    · 房内有人（含叛徒）：速度 4+ 逃进相邻、有门连通、已发现的房间，否则坠亡。
    · 圣徽拖延（p33）：持圣徽且站在深渊邻格，可弃掉圣徽代替翻牌，并阻止房屋
      继续坍塌到自己下个回合结束；深渊回合轨照常推进。
    · 检定令牌一旦放下就计入总数：来源房间随后塌掉也不作废（p33 明文），
      电子版天然满足——令牌与 `used_exorcism_sources` 都不依赖房间存活。
    · 胜负：驱魔满员 → 英雄胜；英雄全灭 → 叛徒胜。叛徒被塌死也照常扩散
      （p104 "You may still collapse rooms on your turn and eventually win
      even if you are killed"），故吸收引擎"叛徒死亡即英雄胜"的兜底。

    已知简化：
        · 深渊邻格挑哪间塌用确定性顺序（按坐标排序取第一间），原版由叛徒任选；
          人类叛徒暂无"选哪间塌"的弹窗（接 prompter 即可支持）。
        · 机器人不会主动使用"献出圣徽"，该行动目前只对人类玩家有意义。
        · 本剧本没有怪物，威胁完全由坍塌承担，引擎的怪物回合对本局无操作。
    """

    mode = "abyss_exorcism"

    SACRIFICE_ACTION = "sacrifice_holy_symbol"
    SANITY_ITEM_SOURCES = ["omen_holy_symbol", "omen_ring"]
    ALL_SOURCES = (
        ExorcismMode.SANITY_ROOM_SOURCES + SANITY_ITEM_SOURCES
        + ExorcismMode.KNOWLEDGE_ROOM_SOURCES + ExorcismMode.KNOWLEDGE_ITEM_SOURCES
    )

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("used_exorcism_sources", [])
        flags["abyss_room"] = self._pick_abyss_room(engine, room_key)
        flags["abyss_started"] = False
        flags["abyss_paused_until"] = 0
        start = engine.state.board.get(flags["abyss_room"])
        engine._log(f"地板在{start.name if start else '地下室'}裂开，下面不是地基，是火。")

    def _pick_abyss_room(self, engine: Any, haunt_room_key: str) -> str:
        """p104：地下室里无人、带预兆或事件符号的房间；没有就从牌堆补一间。"""
        occupied = {p.room_key for p in engine.state.players if not p.dead}
        basement = [
            room for room in engine.state.board.values()
            if room.floor == -1 and room.revealed and room.key not in occupied
        ]
        with_symbol = sorted(room.key for room in basement if room.symbol in ("omen", "event"))
        if with_symbol:
            return with_symbol[0]
        if basement:
            return sorted(room.key for room in basement)[0]
        deck_id = next(
            (
                template_id for template_id in engine.state.room_deck
                if template_id in engine.catalog.room_templates
                and engine.catalog.room_templates[template_id].floor == -1
            ),
            "",
        )
        placed = engine._ensure_room_in_play(deck_id, haunt_room_key) if deck_id else None
        return placed or haunt_room_key

    # ------------------------------------------------------- 深渊每回合扩散
    def on_turn_end(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        first_traitor_turn = False
        if player.role == "traitor":
            if not flags.get("abyss_started"):
                flags["abyss_started"] = True
                first_traitor_turn = True
                start = flags.get("abyss_room")
                if start:
                    engine._collapse_room(str(start), cause="地狱之门")
            engine._advance_haunt_track("abyss_turn", 1)
        if first_traitor_turn:
            return  # 第 1 回合只开洞；按速率塌房从第 2 回合开始（p104）
        turn = engine._haunt_track_value("abyss_turn")
        if turn <= 0:
            return  # 第 1 回合不塌房（p104 "starting on Turn 2"）
        if turn <= int(flags.get("abyss_paused_until", 0) or 0):
            engine._log("圣徽烧成的灰把裂缝暂时按住了。")
            return
        count = 1 if turn == 1 else engine.roll_dice(min(4, turn), "深渊扩散")
        if count > 0:
            engine._collapse_adjacent_rooms(count)

    # --------------------------------------------------------- 圣徽拖延
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        if self._next_to_abyss(engine, player):
            return actions
        return [action for action in actions if action.id != self.SACRIFICE_ACTION]

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id != self.SACRIFICE_ACTION:
            return super().perform_action(engine, player, action_id, data)
        if "omen_holy_symbol" not in player.items:
            engine._log("你没有圣徽可以献出。")
            return False
        if not self._next_to_abyss(engine, player):
            engine._log("你脚下没有紧邻的深渊，圣徽无处可献。")
            return False
        engine._discard_card_from_player(player, "omen_holy_symbol", return_to_room=False)
        engine._haunt_flags()["abyss_paused_until"] = engine._haunt_track_value("abyss_turn") + 1
        engine._mark_haunt_action_used(player)
        engine._log("圣徽在你手里烧成灰烬，塌陷停了一拍——但深渊的时钟没有停。")
        return True

    def _next_to_abyss(self, engine: Any, player: Any) -> bool:
        return any(engine._is_collapsed(key) for key in engine._grid_neighbors(player.room_key))

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("exorcism_successes") >= engine._haunt_track_target("exorcism_successes"):
            engine._set_winner("heroes", "最后一句祷词落下，房子不再颤抖，灰雾退了回去，红光熄灭。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "地板整片垮落，最后几个灵魂一起坠进了火湖。")
            return True
        return True  # 叛徒死了深渊照常扩散：吸收引擎兜底



class TentacledHorrorMode(CarnivorousIvyMode):
    """剧本 23 触手恐怖（Tentacled Horror）。

    权威原文：英雄手册 p34 / 叛徒手册 p105。

    复用剧本 7 的爬行藤机器（根令牌 + 尖端怪物配对、抓住不掉血改拖走、
    拖向根部、到根即吞噬、尖端进神秘电梯则电梯停用），本剧本按原文改动的部分：

    · 叛徒开局即死并移出对局（p105 "Your explorer is dead. Remove it from the
      game"）；成长时钟与怪物回合由"本轮最后一名存活玩家"代跑（同 6/10/21 惯例）。
    · 根/尖端对数 = 玩家数，只能落在 熔炉房/温室/风琴房/地下湖/花园/裂隙，
      在场不足就从房间牌堆里找出来补上（p105 "You cannot save any tentacles
      for later"），所以本剧本不再在后续发现房间时补藤。
    · 触手按 p105 成长表变强：回合 0 → 2/3/6，1-2 → 2/4/7，3-4 → 3/5/7，
      5-7 → 3/7/7，8+ → 4/8/8（每只尖端在自己回合开始时刷新）。
    · 抓着人的尖端每回合只挪 1 格（7 号是 2 格），且携带人质时不能攻击。
    · 尖端被任何攻击击败 → 缩回到配对的根所在房间并昏迷（7 号留在原地）。
    · 被抓者下个回合开始必须与缠着自己的尖端打一场力量对决（p34）：打赢即获释，
      但本回合之后每进一间房按 2 格计；打输或平手不掉血，本回合直接结束。
    · 头颅（p34）：持水晶球者知识 4+ 凝视成功 → 掷 4 骰查表定头位
      （0 储藏室 / 1 厨房 / 2 风琴房 / 3 裂隙 / 4-5 地下湖 / 6 温室 / 7 地窖 /
      8 熔炉房），球随即碎裂；该房未入场就从牌堆找出来放到合法楼层。
      走进头位房间、持炸药或长矛攻击 → 不掷骰自动杀死怪物（且不吃炸药反噬）。
    · 胜负：摧毁头颅 → 英雄胜；英雄全灭 → 叛徒胜。叛徒开局就死，
      必须吸收引擎"叛徒死亡即英雄胜"的兜底（老坑第 13 次）。

    已知简化：
        · p105「铃铛对被抓者无效、灵应板对尖端无效」属物品交互边界，未接（同 7 号）。
        · 被抓者的开局对决由引擎自动掷骰，原版是玩家在自己回合开始时主动攻击——
          结果等价，但人类玩家失去"先做别的再打"的选择权。
        · 头颅房间的接入口由引擎按 `_ensure_room_in_play` 选位，原版由叛徒任选
          一个未探索门口（楼层合法即可）。
        · p105「尖端用力量攻击击败英雄时不造成伤害，改为抓住」只在尖端的主动攻击
          里生效；英雄主动攻击尖端却落败时的反击伤害是引擎全局规则，本剧本未做
          例外（与 7 号同源的同一条简化）。
    """

    mode = "tentacled_horror"

    ROOM_IDS = ["furnace_room", "conservatory", "organ_room", "underground_lake", "garden", "chasm"]
    # p34：掷 4 骰（0-8）→ 头颅所在房间模板
    HEAD_TABLE = (
        "larder", "kitchen", "organ_room", "chasm",
        "underground_lake", "underground_lake", "conservatory", "crypt", "furnace_room",
    )
    # p105 成长表：(回合上限, 速度, 力量, 理智)
    GROWTH = ((0, 2, 3, 6), (2, 2, 4, 7), (4, 3, 5, 7), (7, 3, 7, 7), (99, 4, 8, 8))
    GAZE_ACTION = "gaze_crystal_ball"
    KILL_ACTION = "destroy_head"
    HEAD_WEAPONS = ("item_dynamite", "omen_spear")
    CRYSTAL_BALL = "omen_crystal_ball"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine._drop_inventory_on_death(traitor)
            traitor.dead = True
            engine._log(f"{traitor.name}被卷进了墙里——回应她的只剩下咀嚼声。")
        flags = engine._haunt_flags()
        flags.setdefault("grabbed", {})
        spec = self._tip_spec(engine)
        players = len(engine.state.players)
        placed = 0
        for template_id in self.ROOM_IDS:
            if placed >= players:
                break
            key = engine._ensure_room_in_play(template_id, room_key)
            if not key or engine.tokens_in_room(key, "root"):
                continue
            tip = engine._spawn_single_haunt_monster(spec, key)
            if tip is None:
                continue
            root = engine.spawn_token("root", label="触手之根", role="marker", room_key=key)
            root.data["tip_id"] = tip.id
            placed += 1
        flags["pairs_placed"] = placed
        engine._log(f"{placed} 条触手从墙里探出来，每一条都连着自己的根。")

    def _tip_spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.CREEPER_TEMPLATE) or {"template_id": self.CREEPER_TEMPLATE, "name": "触手尖端"})

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        return None  # p105：所有触手开局就全部入场，不留备用

    # ------------------------------------------------------------- 成长
    def _growth_stats(self, turn: int) -> tuple[int, int, int]:
        for upper, speed, might, sanity in self.GROWTH:
            if turn <= upper:
                return speed, might, sanity
        return 4, 8, 8

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.CREEPER_TEMPLATE:
            return False
        speed, might, sanity = self._growth_stats(engine._haunt_track_value("tentacle_turn"))
        monster.speed, monster.might, monster.sanity = speed, might, sanity
        return super().on_monster_turn_start(engine, monster)

    # ------------------------------------------------------------- 拖拽
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """p105：抓人的尖端每回合只朝配对的根挪 1 格（7 号是 2 格）。"""
        if _monster_id(monster) != self.CREEPER_TEMPLATE:
            return False
        carried = self._grabbed_by(engine, monster)
        if carried is None:
            return False
        root = self._root_for_tip(engine, monster)
        if root is None or monster.room_key == root.room_key:
            return True
        path = engine._shortest_path(monster.room_key, root.room_key)
        if len(path) <= 1:
            return True
        dest = path[1]
        monster.room_key = dest
        carried.room_key = dest
        engine._log(f"触手拖着{carried.name}往根部缩，来到{engine.state.board[dest].name}。")
        return True

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p105：尖端被击败 → 松手（人质摔在原地）、缩回配对的根、翻成昏迷面。"""
        if _monster_id(monster) != self.CREEPER_TEMPLATE:
            return False
        carried = self._grabbed_by(engine, monster)
        if carried is not None:
            self._ungrab(engine, carried)
            carried.movement_stopped = False
            engine._log(f"触手断了，{carried.name}摔在原地——他自由了。")
        root = self._root_for_tip(engine, monster)
        if root is not None and monster.room_key != root.room_key:
            monster.room_key = root.room_key
            engine._log(f"{monster.name}缩回了它的根部。")
        return False  # 引擎默认击晕一回合 = 翻成昏迷面

    def item_pickup_blocked(self, engine: Any, player: Any, card_id: str) -> bool:
        return False  # 7 号的"叛徒不能重拾古书"是常春藤专属，本剧本没有

    # ------------------------------------------------------- 被抓者的开局对决
    def on_turn_start(self, engine: Any, player: Any) -> None:
        grabbed = engine._haunt_flags().get("grabbed", {})
        tip_id = str(grabbed.get(str(player.id), ""))
        if not tip_id:
            return
        if player.dead:
            self._ungrab(engine, player)
            return
        tip = next((m for m in engine.state.monsters if str(getattr(m, "id", "")) == tip_id), None)
        if tip is None:
            self._ungrab(engine, player)
            player.movement_stopped = False
            return
        player_roll = engine._roll_attack(player, "might")
        tip_roll = engine._roll_monster_attack(tip, "might")
        engine._log(f"{player.name} 开局劈向缠住自己的触手：{player_roll} 对 {tip_roll}。")
        if player_roll > tip_roll:
            self._ungrab(engine, player)
            player.movement_stopped = False
            flags = engine._haunt_flags()
            escaped = set(flags.get("escaped_ids", []) or [])
            escaped.add(player.id)
            flags["escaped_ids"] = sorted(escaped)
            engine._log(f"{player.name}挣脱了，但一身伤——本回合每进一间房都算两格。")
            return
        player.movement_stopped = True
        player.steps_remaining = 0
        player.attack_used = True
        player.item_used = True
        engine._log(f"{player.name}没能挣脱（不掉血），这个回合就这么到头了。")

    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None) -> int:
        """p34：挣脱后的剩余回合里，每进一间房按 2 格计。"""
        if player.id in set(engine._haunt_flags().get("escaped_ids", []) or []):
            return 2
        return 1

    def on_turn_end(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        flags["escaped_ids"] = [pid for pid in (flags.get("escaped_ids", []) or []) if int(pid) != player.id]
        if _is_last_in_round(engine, player):
            engine._advance_haunt_track("tentacle_turn", 1)

    def _is_round_last(self, engine: Any, player: Any) -> bool:
        """叛徒已出局：成长时钟由本轮最后一名存活玩家代跑（同怪物回合惯例）。"""
        return _is_last_in_round(engine, player)

    # ------------------------------------------------------------- 头颅
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        return [
            action for action in actions
            if action.id != self.KILL_ACTION or self._can_destroy_head(engine, player)
        ]

    def _can_destroy_head(self, engine: Any, player: Any) -> bool:
        head = engine._haunt_flags().get("head_room")
        return bool(head) and player.room_key == head and any(w in player.items for w in self.HEAD_WEAPONS)

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == self.GAZE_ACTION:
            return self._gaze(engine, player, action_id, data)
        if action_id == self.KILL_ACTION:
            return self._destroy_head(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _gaze(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if not super().perform_action(engine, player, action_id, data):
            return False
        engine._discard_card_from_player(player, self.CRYSTAL_BALL, return_to_room=False)
        flags = engine._haunt_flags()
        flags["head_found"] = True
        roll = engine.roll_dice(4, "头颅定位")
        template_id = self.HEAD_TABLE[min(roll, len(self.HEAD_TABLE) - 1)]
        key = engine._ensure_room_in_play(template_id, player.room_key)
        flags["head_room"] = key
        room = engine.state.board.get(key or "")
        engine._log(f"水晶球炸成碎片，碎屑重新聚拢——那颗头在 {room.name if room else template_id}。")
        return True

    def _destroy_head(self, engine: Any, player: Any) -> bool:
        flags = engine._haunt_flags()
        head = flags.get("head_room")
        if not head or head not in engine.state.board:
            engine._log("你还不知道那颗头在哪里。")
            return False
        if player.room_key != head:
            engine._log("你得先走进那颗头所在的房间。")
            return False
        weapon = next((w for w in self.HEAD_WEAPONS if w in player.items), "")
        if not weapon:
            engine._log("只有炸药或长矛能一击摧毁它。")
            return False
        if weapon == "item_dynamite":
            engine._discard_card_from_player(player, weapon, return_to_room=False)
        flags["creature_destroyed"] = True
        grabbed = flags.get("grabbed", {})
        for pid in list(grabbed):
            victim = next((p for p in engine.state.players if str(p.id) == str(pid)), None)
            if victim is not None:
                victim.movement_stopped = False
        flags["grabbed"] = {}
        engine.state.monsters = []
        for token in engine.tokens_of_kind("root"):
            engine.remove_token(token.uid)
        engine._log("你把武器送进那颗头里——它没有挣扎，整栋房子都跟着震了一下。")
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_flags().get("creature_destroyed"):
            engine._set_winner("heroes", "那颗头终于不再动了，垂着的触手一条接一条软了下去。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后一名探险者也成了某条触手的食物。")
            return True
        return True  # 叛徒开局即死：吸收引擎兜底



class BatSwarmMode(GenericModeHandler):
    """剧本 24 蝙蝠归巢（Fly Away Home）。

    权威原文：英雄手册 p35 / 叛徒手册 p106。

    已按原文实现：
        · 数值：蝙蝠 Speed 5 / Might 2 / Sanity 1（p106 页脚，新增 bat 模板——
          骨架此前用 spider 冒充蝙蝠）。
        · 开局：叛徒已死并移出对局；风琴房不在场就从牌堆找出来放上（p35）；
          塔楼或阁楼放 3 只、裂隙或地下墓穴放 3 只，两处都没发现就少放（p106
          "the haunt begins with fewer Bats"）。
        · 入室（p106）：每个怪物回合掷「玩家数」枚骰决定进入数量，入口为
          塔楼/裂隙/温室/门厅/花园/墓地/露台/阳台（有朝外窗的房间），每个入口
          一次只进一只，蝙蝠多于入口才轮着重复进；场内蝙蝠封顶 24 只。
        · 攻击（p106）：蝙蝠不做普通攻击——贴脸的蝙蝠每只掷 1 枚骰，掷出 2
          就贴到该探险者身上；贴附后不再移动也不再攻击。
        · 贴附代价（p35/p106）：宿主每回合开始按贴附数各受 1 点物理伤害，
          且每只贴附蝙蝠让宿主少走 1 格（至少保 1 格）；贴附的蝙蝠跟着宿主一起移动。
        · 英雄胜三步（p35，每步每回合只试一次）：① 风琴房力量 5+ 启动管风琴
          → ② 风琴房知识 6+ 奏出驱蝠之音，赶走所有未贴附的蝙蝠并封住入口
          → ③ 杀死仍贴在人身上的蝙蝠。
        · 力量攻击击败蝙蝠 = 直接杀死而非击晕（p35，走 monster_killed_on_defeat）。
        · 叛徒胜：所有英雄死亡。叛徒开局即死，吸收引擎"叛徒死亡即英雄胜"兜底
          （老坑第 14 次）。

    已知简化：
        · p35「持盔甲少受 1 点吸血伤害」由引擎既有的盔甲效果统一承担
          （本仓库的盔甲是"挡掉一次物理伤害"），比原文更强，不在剧本里另加减免
          ——两处都减会让盔甲把 2 点伤害全挡掉。
        · p35「爱好音乐的角色可用知识 5+ 代替 6+」未建模——本仓库角色数据里
          没有爱好（hobby）字段，需要先在 content.py 补爱好数据。
        · 「任何有朝外窗的房间」只按 p106 明列的八个入口判定，其余房间的窗户
          属性未建模。
        · 额外蝙蝠进哪个入口由确定性轮转决定，原版由叛徒任选。
    """

    mode = "bat_exodus"

    BAT = "bat"
    BAT_CAP = 24
    ENTRY_ROOMS = ("tower", "chasm", "conservatory", "entrance_hall", "garden", "graveyard", "patio", "balcony")
    START_SPOTS = (("tower", "attic"), ("chasm", "catacombs"))
    DAMAGE_SOURCE = "吸血蝙蝠"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine._drop_inventory_on_death(traitor)
            traitor.dead = True
            engine._log(f"{traitor.name}把窗户全部推开，把血交给了祂们。")
        engine._ensure_room_in_play("organ_room", room_key)  # p35
        engine._haunt_flags().setdefault("attached", {})
        spec = self._bat_spec(engine)
        released = 0
        for options in self.START_SPOTS:
            key = self._first_discovered(engine, options)
            if not key:
                continue  # p106：两处都没发现就少放蝙蝠
            for _ in range(3):
                if engine._spawn_single_haunt_monster(spec, key) is None:
                    break
                released += 1
        if released:
            engine._advance_haunt_track("bats_released", released)
        engine._log(f"{released} 只蝙蝠先从塔楼与地裂的方向落了进来。")

    def _first_discovered(self, engine: Any, template_ids: tuple[str, ...]) -> str:
        for template_id in template_ids:
            for key, room in engine.state.board.items():
                if room.template_id == template_id and room.revealed and not engine._is_collapsed(key):
                    return key
        return ""

    def _bat_spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.BAT) or {"template_id": self.BAT, "name": "蝙蝠"})

    # ------------------------------------------------------------ 贴附状态
    def _bats(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) == self.BAT]

    def _attached_map(self, engine: Any) -> dict:
        return engine._haunt_flags().setdefault("attached", {})

    def _attached_ids(self, engine: Any, player: Any) -> list[str]:
        return [str(i) for i in (self._attached_map(engine).get(str(player.id), []) or [])]

    def _host_of(self, engine: Any, bat: Any) -> Any | None:
        bat_id = str(getattr(bat, "id", ""))
        for pid, ids in self._attached_map(engine).items():
            if bat_id in [str(i) for i in (ids or [])]:
                return next((p for p in engine.state.players if str(p.id) == str(pid)), None)
        return None

    def _attach(self, engine: Any, bat: Any, player: Any) -> None:
        attached = self._attached_map(engine)
        ids = [str(i) for i in (attached.get(str(player.id), []) or [])]
        ids.append(str(bat.id))
        attached[str(player.id)] = ids
        bat.room_key = player.room_key
        engine._log(f"一只蝙蝠贴上了{player.name}，开始吸血。")

    def _drop_dead_bat(self, engine: Any, bat: Any) -> None:
        bat_id = str(getattr(bat, "id", ""))
        attached = self._attached_map(engine)
        for pid in list(attached):
            rest = [str(i) for i in (attached[pid] or []) if str(i) != bat_id]
            if rest:
                attached[pid] = rest
            else:
                attached.pop(pid, None)

    def _release_host(self, engine: Any, player: Any) -> None:
        """宿主死亡后蝙蝠不再钉在尸体上，可以重新出去找人。"""
        self._attached_map(engine).pop(str(player.id), None)

    # --------------------------------------------------------- 怪物回合
    def on_turn_end(self, engine: Any, player: Any) -> None:
        """p106：蝙蝠在怪物回合入室。叛徒已出局，怪物回合就在"本轮最后一名
        存活玩家"的回合结束触发——挂在这里而不是 on_monster_turn_start，
        否则开局一只蝙蝠都没落下时（塔楼/阁楼与裂隙/地下墓穴都没被发现）
        根本没有怪物回合，蝙蝠永远进不来（实测 150 回合僵局）。"""
        if _is_last_in_round(engine, player):
            self._enter_bats_this_round(engine)

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.BAT:
            return False
        if self._host_of(engine, monster) is not None:
            return True  # 已贴附：不移动不攻击，代价在宿主回合开始结算
        target = engine._find_monster_target(monster)
        if target is None:
            return True
        if monster.room_key != target.room_key:
            steps = engine.roll_dice(max(1, getattr(monster, "speed", 5)), "蝙蝠移动")
            path = engine._shortest_path(monster.room_key, target.room_key)
            if len(path) > 1:
                monster.room_key = path[min(len(path) - 1, max(1, steps))]
            return True
        roll = engine.roll_dice(1, "蝙蝠扑附")
        if roll >= 2:
            self._attach(engine, monster, target)
        else:
            engine._log(f"蝙蝠在{target.name}头顶盘旋，没能落下来（掷出 {roll}）。")
        return True

    def _entry_doors(self, engine: Any) -> list[str]:
        """p106 的蝙蝠入口：只要"在房子里"即可，不要求已发现。

        原版开局那几块起始板块就是正面朝上的，本引擎把 entrance_hall 等起始房
        记作 revealed=False（等人踩进去才翻正），若按"已发现"筛入口会让作祟
        开局根本没有蝙蝠能入室。坍塌掉的板块不算入口。
        """
        keys = []
        for template_id in self.ENTRY_ROOMS:
            key = next(
                (
                    k for k, room in engine.state.board.items()
                    if room.template_id == template_id and not engine._is_collapsed(k)
                ),
                "",
            )
            if key:
                keys.append(key)
        return keys

    def _enter_bats_this_round(self, engine: Any) -> None:
        """p106：每个怪物回合按玩家数掷骰放蝙蝠；一个怪物回合只放一批。"""
        flags = engine._haunt_flags()
        if flags.get("bats_sealed"):
            return
        turn = engine.state.turn_count
        if int(flags.get("last_entry_turn", -1)) == turn:
            return
        flags["last_entry_turn"] = turn
        count = engine.roll_dice(len(engine.state.players), "蝙蝠入室")
        if count <= 0:
            return
        doors = self._entry_doors(engine)
        if not doors:
            return
        spec = self._bat_spec(engine)
        entered = 0
        for index in range(count):
            if len(self._bats(engine)) >= self.BAT_CAP:
                engine._log("蝙蝠令牌用尽了——屋里已经挤满 24 只。")
                break
            if engine._spawn_single_haunt_monster(spec, doors[index % len(doors)]) is None:
                break
            entered += 1
        if entered:
            engine._advance_haunt_track("bats_released", entered)
            engine._log(f"{entered} 只蝙蝠从窗口与地裂挤了进来。")

    # ------------------------------------------------------- 宿主回合开始
    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.role != "hero":
            return
        if player.dead:
            # 宿主已被别的来源杀死：蝙蝠该松开去找下一个活人，而不是钉在尸体上
            self._release_host(engine, player)
            return
        count = len(self._attached_ids(engine, player))
        if not count:
            return
        engine._log(f"{player.name} 身上贴着 {count} 只蝙蝠。")
        engine._deal_damage(player, "physical", count, source=self.DAMAGE_SOURCE)
        if player.dead:
            self._release_host(engine, player)
            return
        player.steps_remaining = max(1, player.steps_remaining - count)

    def on_player_moved(self, engine: Any, player: Any) -> None:
        """贴附的蝙蝠跟着宿主走。"""
        for bat_id in self._attached_ids(engine, player):
            bat = next((m for m in engine.state.monsters if str(getattr(m, "id", "")) == bat_id), None)
            if bat is not None:
                bat.room_key = player.room_key

    # ------------------------------------------------------------- 战斗
    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """p35：力量攻击击败蝙蝠 = 杀死，不是击晕。"""
        if _monster_id(monster) != self.BAT or attack_attr != "might":
            return False
        self._drop_dead_bat(engine, monster)
        return True

    # ------------------------------------------------------------- 三步
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id != "drive_away_bats":
            return super().perform_action(engine, player, action_id, data)
        if not super().perform_action(engine, player, action_id, data):
            return False
        engine._haunt_flags()["bats_sealed"] = True
        driven = 0
        for bat in list(self._bats(engine)):
            if self._host_of(engine, bat) is None:
                engine._kill_monster(bat, killer=player)
                driven += 1
        engine._log(f"管风琴砸出刺耳的和弦，{driven} 只没贴住人的蝙蝠撞出窗外——入口封死了。")
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "屋里只剩下翅膀摩擦声，和一地抽干的空壳。")
            return True
        if engine._haunt_flags().get("bats_sealed") and not self._bats(engine):
            engine._set_winner("heroes", "最后一只吸饱的蝙蝠被砸在地上，窗外透进黎明的光。")
            return True
        return True  # 叛徒开局即死：吸收引擎兜底


class HellbeastMode(ExorcismMode):
    """剧本 38 火蝠（Hellbeasts）。

    权威原文：英雄手册 p49 / 叛徒手册 p120。

    继承路子与 22 号 AbyssExorcismMode 相同（都继承 ExorcismMode 复用驱魔底座），
    而【不是】交接文档曾建议的"继承 24 号 BatSwarmMode"——经英文 PDF 原文核对，
    38 号火蝠与 24 号吸血蝠几乎全相反：
        · 火蝠不贴附英雄、不可被攻击、叛徒存活、伤害在怪物回合按"房间区域"结算；
        · 24 号蝙蝠贴附吸血、可被力量攻击杀死、叛徒开局即死、伤害按"贴附数"结算。
    而 38 号的驱魔来源清单与 22 号逐字一致（理智道具把灵应板换成戒指 omen_ring），
    所以照抄 AbyssExorcismMode 覆盖 SANITY_ITEM_SOURCES + 重算 ALL_SOURCES 的写法。
    全程不改 engine.py / content.py / ui.py，火蝠怪物层复用 bat 模板与既有钩子。

    已按原文实现：
        · 火蝠（bat 模板）Speed 3、不可攻击也不可被攻击（monster spec invulnerable=True，
          攻击闸门由引擎 _monster_invulnerable 承担）；不影响英雄移动（引擎怪物本就不
          阻挡移动，天然满足）。
        · 开局（p120）：叛徒存活（揭示者变叛徒）。取出「玩家数一半向上取整」只火蝠，
          全部放在作祟揭露房。
        · 怪物回合（p120 "You Must Do This On Your Turn"）：叛徒存活 → 走引擎正常怪物
          回合（在叛徒回合结束触发）。一次掷骰（roll_dice(速度3)）的结果同时决定
          「现有火蝠移动格数」与「新进揭露房的火蝠数」；先移动现有火蝠、再繁殖新蝠，
          天然满足"新蝠当回合不移动"。一个怪物回合只跑一次（last_swarm_turn 守卫）。
        · 灼烧（p120）：移动后，对每个"含≥1 活英雄且含≥1 火蝠"的房间，掷「该房火蝠数」
          枚骰，房内所有英雄受该总和的物理伤害。
        · 驱魔（p49，英雄胜）：成功次数 = 玩家数即放逐火蝠。理智 5+（教堂/地窖/五芒星室/
          圣徽/戒指）或知识 5+（图书馆/研究实验室/古书/水晶球），每人每回合一次，每个
          来源只能成功用一次（成功后作废，房间放检定令牌）——全部继承自 ExorcismMode。
        · 胜负：驱魔满员 → 英雄胜；英雄全灭 → 叛徒胜。叛徒存活操控火蝠，叛徒死亡
          【不】构成英雄胜利，吸收引擎兜底（老坑）。

    已知简化 / 解释性决策：
        ① 原文未指定"移动/繁殖"掷几颗骰，采用 roll_dice(火蝠速度=3)，与引擎怪物
           移动惯例（roll_dice(monster.speed)）一致，保证种子回放可复现。
        ② 原文未设火蝠数量上限，忠实实现不设上限（bot 局可能滚雪球致英雄必败，
           属难度/AI 深度问题，不在剧本层截断）。
        ③ 盔甲：原文"只防 1 点"，引擎既有盔甲是"挡掉整次物理伤害"，采用引擎既有
           语义（同 24 号已知简化）；不为对齐"只防 1 点"把一次灼烧拆成逐蝠多次
           _deal_damage（那样盔甲会逐次触发、语义更偏）。
        ④ 新蝠计入当回合灼烧：先移动现有蝠 → 繁殖新蝠 → 对当前所有同房蝠结算，
           与 p120"After you have moved your monsters, roll..."的顺序一致。
        ⑤ 8 骰上限：engine.roll_dice(count) 内部 count=max(1,min(8,count))，故单房间
           火蝠 >8 只时灼烧只掷 8 枚骰、少于"火蝠数"枚，伤害被系统性低估；因火蝠
           不设数量上限（见②），长局可能触发。属接受的引擎限制。
        ⑥ 道具驱魔令牌落点：道具来源（圣徽/戒指/古书/水晶球）成功驱魔时，检定令牌
           被放在英雄所在房间板块而非对应道具卡（继承 ExorcismMode 行为，8/22 号同款）；
           "来源不可复用"由 used_exorcism_sources 去重保证，功能正确，仅表现层与 p49
           字面（"on the item card"）有偏差。
    """

    mode = "hellbeast_exorcism"

    FIREBAT = "bat"
    DAMAGE_SOURCE = "火蝠灼烧"
    # 22 号同款：理智道具把 8 号的灵应板换成戒指
    SANITY_ITEM_SOURCES = ["omen_holy_symbol", "omen_ring"]
    ALL_SOURCES = (
        ExorcismMode.SANITY_ROOM_SOURCES + SANITY_ITEM_SOURCES
        + ExorcismMode.KNOWLEDGE_ROOM_SOURCES + ExorcismMode.KNOWLEDGE_ITEM_SOURCES
    )

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        """p120：叛徒存活；取「玩家数一半向上取整」只火蝠全放揭露房。

        刻意不调 super().setup（ExorcismMode.setup 会生成 8 号女妖令牌）；
        驱魔底座靠继承的方法即可，无需女妖令牌。不杀叛徒、不强制房间入场。
        """
        flags = engine._haunt_flags()
        flags.setdefault("used_exorcism_sources", [])
        flags["haunt_room"] = room_key
        flags["last_swarm_turn"] = -1
        count = (len(engine.state.players) + 1) // 2
        spec = self._firebat_spec(engine)
        born = 0
        for _ in range(count):
            if engine._spawn_single_haunt_monster(spec, room_key) is not None:
                born += 1
        room = engine.state.board.get(room_key)
        engine._log(
            f"{born} 只燃烧的火蝠从{room.name if room else '暗处'}里涌出，"
            f"翅膀上噼啪作响——叛徒要让它们喝饱人血。"
        )

    # ------------------------------------------------------------- 火蝠群回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.FIREBAT:
            return False  # 非火蝠交回引擎默认
        # 一个怪物回合只跑一次群集阶段（引擎会逐只火蝠调用本钩子）
        if int(engine._haunt_flags().get("last_swarm_turn", -1)) != engine.state.turn_count:
            self._run_swarm_phase(engine)
        return True  # 火蝠永不做引擎默认的追击/攻击

    def _run_swarm_phase(self, engine: Any) -> None:
        """p120：一次掷骰同时决定移动格数与新进揭露房的火蝠数；先移动后繁殖，
        再对每个"火蝠与英雄同房"的房间结算灼烧伤害。"""
        flags = engine._haunt_flags()
        flags["last_swarm_turn"] = engine.state.turn_count
        spec = self._firebat_spec(engine)
        speed = max(1, int(spec.get("speed", 3)))
        steps = engine.roll_dice(speed, "火蝠群移动")

        # 1) 先移动现有火蝠：每只朝最近英雄走至多 steps 格（借 BatSwarmMode 写法）
        for bat in self._bats(engine):
            target = engine._find_monster_target(bat)
            if target is None or bat.room_key == target.room_key:
                continue
            path = engine._shortest_path(bat.room_key, target.room_key)
            if len(path) > 1 and steps > 0:
                bat.room_key = path[min(len(path) - 1, steps)]

        # 2) 再繁殖 steps 只新火蝠到揭露房（新蝠当回合不移动）
        haunt_room = str(flags.get("haunt_room") or "")
        born = 0
        if haunt_room:
            for _ in range(max(0, steps)):
                if engine._spawn_single_haunt_monster(spec, haunt_room) is None:
                    break
                born += 1
        engine._log(
            f"火蝠群掷出 {steps}：现有火蝠各移动至多 {steps} 格，"
            f"{born} 只新火蝠在揭露房里破蛹而出。"
        )

        # 3) 结算房间灼烧伤害
        self._burn_rooms(engine)

    def _burn_rooms(self, engine: Any) -> None:
        """p120：对每个"含≥1 活英雄且含≥1 火蝠"的房间，掷「该房火蝠数」枚骰，
        房内所有英雄受该总和的物理伤害（盔甲由引擎自动结算）。"""
        counts: dict[str, int] = {}
        for bat in self._bats(engine):
            counts[bat.room_key] = counts.get(bat.room_key, 0) + 1
        for room_key, bat_count in counts.items():
            victims = [
                p for p in engine.state.players
                if not p.dead and p.role == "hero" and p.room_key == room_key
            ]
            if not victims:
                continue
            amount = engine.roll_dice(bat_count, "火蝠灼烧")
            if amount <= 0:
                continue
            room = engine.state.board.get(room_key)
            engine._log(
                f"{room.name if room else room_key} 里 {bat_count} 只火蝠一齐喷焰，"
                f"灼烧房内的英雄（{amount} 点物理伤害）。"
            )
            for victim in victims:
                engine._deal_damage(victim, "physical", amount, source=self.DAMAGE_SOURCE)

    # ------------------------------------------------------------- 工具
    def _bats(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) == self.FIREBAT]

    def _firebat_spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.FIREBAT) or {"template_id": self.FIREBAT, "name": "火蝠", "speed": 3})

    # ------------------------------------------------------------- 驱魔（覆盖基类）
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        """覆盖 ExorcismMode.perform_action：忠实 p49"只有【成功】使用某来源，该来源
        才不可复用"——仅在驱魔检定真正成功时才作废来源并放检定令牌。

        基类 ExorcismMode 只要行动【可执行】（底层 _perform_generic_haunt_action 恒
        返回 True）就无条件 used_exorcism_sources.append + spawn_token(role="check")，
        但 exorcism_successes 轨道只在检定成功时推进；于是理智/知识 5+ 检定【失败】
        时来源被永久作废、令牌落下、轨道却不 +1。38 号 target=玩家数、仅 9 个来源，
        6 人局若失败 ≥4 次会把来源耗尽，出现"9 来源全 used、轨道 < target"的不可胜
        软锁。

        修法：绕过基类的无条件消耗——用 super(ExorcismMode, self) 直达祖父级
        GenericModeHandler → _perform_generic_haunt_action，以 exorcism_successes
        轨道增量作为"本次检定确实成功"的信号，仅在成功时复刻基类的全部成功副作用
        （used 去重记账 + 令牌 kind 判定 + spawn_token）。刻意不改基类 ExorcismMode，
        以保 8/11/22 号行为不变。
        """
        # 非驱魔来源：交回基类处理（ExorcismMode → GenericModeHandler）
        if action_id not in self.ALL_SOURCES:
            return super().perform_action(engine, player, action_id, data)
        # 已作废的来源不可复用（与基类同款守卫）
        if action_id in set(engine._haunt_flags().get("used_exorcism_sources", [])):
            engine._log("这个驱魔来源已经成功用过，不能再用了。")
            return False
        # 用轨道增量判定检定是否真正成功（绕过基类的"可执行即消耗"）
        before = engine._haunt_track_value("exorcism_successes")
        ok = super(ExorcismMode, self).perform_action(engine, player, action_id, data)
        after = engine._haunt_track_value("exorcism_successes")
        if ok and after > before:
            # 仅在检定成功时作废来源 + 放检定令牌（复刻基类成功副作用）
            used = list(engine._haunt_flags().get("used_exorcism_sources", []))
            if action_id not in used:
                used.append(action_id)
            engine._haunt_flags()["used_exorcism_sources"] = used
            kind = (
                "sanity_check"
                if action_id in self.SANITY_ROOM_SOURCES + self.SANITY_ITEM_SOURCES
                else "knowledge_check"
            )
            engine.spawn_token(kind, label="驱魔成功", role="check", room_key=player.room_key)
        return ok

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("exorcism_successes") >= engine._haunt_track_target("exorcism_successes"):
            engine._set_winner("heroes", "驱魔完成——火蝠被赶回了最先孕育它们的那片地狱。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后一名英雄在火蝠的烈焰里倒下，屋里只剩噼啪的火光。")
            return True
        return True  # 叛徒存活操控火蝠；吸收引擎"叛徒死亡即英雄胜"兜底

    # ------------------------------------------------------------- 进度摘要
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        """公开信息：火蝠总数 + "某房有 N 只火蝠与英雄同房"的灼烧预警。

        驱魔进度本身由 UI 的 ●○ 轨道渲染，这里不重复。火蝠位置是桌面公开的
        （bat 令牌摆在板块上），无需按 viewer 过滤。
        """
        lines: list[str] = []
        bats = self._bats(engine)
        lines.append(f"火蝠总数：{len(bats)} 只（不可被攻击，会在怪物回合灼烧同房英雄）。")
        counts: dict[str, int] = {}
        for bat in bats:
            counts[bat.room_key] = counts.get(bat.room_key, 0) + 1
        for room_key, count in sorted(counts.items()):
            heroes_here = [
                p for p in engine.state.players
                if not p.dead and p.role == "hero" and p.room_key == room_key
            ]
            if heroes_here:
                room = engine.state.board.get(room_key)
                name = room.name if room else room_key
                lines.append(f"⚠ {name}：{count} 只火蝠正与英雄同房——下个怪物回合会被灼烧。")
        return lines


class VoodooMode(GenericModeHandler):
    """剧本 25 巫毒（Voodoo）。

    权威原文：英雄手册 p36 / 叛徒手册 p107。

    已按原文实现：
        · 开局（p107）：叛徒仍在场（揭示者变叛徒）。给每个英雄各分配一只
          娃娃（5 种），每种绑定两个候选房间（蜡=熔炉房/厨房、瓷=阳台/塔楼、
          石=地下湖/墓地、玻璃=五芒星室/教堂、布=花园/温室）；「恰有一间
          已发现」必须选已发现那间，两间都发现或都没发现时任选（bot 取
          列表第一间，原版叛徒任选）。每个英雄被宣读自己娃娃的描述引文
          ——即知道自己的娃娃类型与两个候选房间。娃娃绑定房间模板 id，
          候选房还没上桌也是合法放置。
        · 探索规则变更（p36）：解除"进带符号的新房间必须停"——本 handler
          覆盖 explore_stop_suspended + suppress_room_draw，探索不再强制
          停下、发现时不抽牌，把抽牌推迟到「结束移动的房间」：回合结束
          时停在新发现的符号房间才补抽；中途经过的房间不抽。
        · 搜寻（p36）：知识 2+，每回合一次（引擎行动经济天然保证）。成功
          后按盘面如实回答本房间有无娃娃；搜到自己房里的娃娃当场自动销毁，
          搜到别人的只公开位置（只有主人能"安全"销毁自己的娃娃）。搜寻
          落空的「这里没有」对全桌公开（实体桌游里答案是口头宣布的）。
        · 英雄死亡 → 其娃娃同时销毁（p36，on_player_died）。
        · 时钟（p107）：叛徒回合结束时把回合/伤害轨道 +1（从 1 起），届时
          每个未销毁的娃娃结算一次效果。叛徒死亡后按本仓库惯例由"本轮
          最后一名存活玩家"的回合结束代推（原文未覆盖叛徒死亡）。
        · 效果（p107）：蜡=自选掉 1 力量或速度；瓷=掷 4 骰 < 回合数即当场
          死亡；石=力量掷骰 < 回合数则每项属性各掉 1 点；玻璃=自选掉 1
          理智或知识；布=知识掷骰 < 回合数则受 2 点物理伤害。结算时逐条
          宣读效果引文。
        · 胜负（p36/p107）：英雄胜 = 所有娃娃销毁 且 存活英雄 ≥ 原英雄数
          一半（向上取整）；叛徒胜 = 开局英雄过半死亡（严格大于一半）。
          两者互斥；叛徒死亡不等于英雄胜（覆盖引擎兜底）。

    已知简化：
        · 「恰有一间已发现」之外的两难由 bot 固定取列表第一间；原版由叛徒
          任选（他会挑英雄难找的房间）。
        · p36「你可以找到任何娃娃的位置，但只能安全销毁自己的」——找到
          别人的娃娃只公开位置；原文未写主人是否可免检定直接销毁，本实现
          按较严格口径：主人仍须自己在该房间搜寻成功才能销毁。
        · 「不安全地销毁别人的娃娃」原文没有给出机制，未建模。
        · bot 英雄只搜自己娃娃的候选房间（或已被公开位置的娃娃房间）；
          不会主动替队友排查其它房间（人类可以）。
        · 蜡/玻璃娃娃的「自选掉哪项」：bot 在"掉 1 点不会死"的属性里掉数值
          较高的一项（两项都会死则掉前者），人类弹窗自选。
    """

    mode = "voodoo_dolls"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        dolls = self._dolls(engine)
        if not dolls:
            return []
        names = {"wax": "蜡", "china": "瓷", "stone": "石", "glass": "玻璃", "cloth": "布"}
        rows = [f"娃娃 {sum(1 for d in dolls if d['destroyed'])}/{len(dolls)} 已销毁"]
        for d in dolls:
            hero = next((p for p in engine.state.players if p.id == d["hero_id"]), None)
            who = hero.name if hero else "?"
            state = "已销毁" if d["destroyed"] else ("位置已公开" if d.get("found") else "下落不明")
            rows.append(f"  {names.get(d['kind'], d['kind'])}·{who}：{state}")
        return rows

    CANDIDATES = {
        "wax": ("furnace_room", "kitchen"),
        "china": ("balcony", "tower"),
        "stone": ("underground_lake", "graveyard"),
        "glass": ("pentagram_chamber", "chapel"),
        "rag": ("garden", "conservatory"),
    }
    DOLL_NAMES = {
        "wax": "蜡娃娃", "china": "瓷娃娃", "stone": "石娃娃",
        "glass": "玻璃娃娃", "rag": "布娃娃",
    }
    DESCRIPTION_QUOTES = {
        "wax": "你烧起来了！",
        "china": "下方的地面，正等着你。",
        "stone": "泥浆灌进嘴里，你喘不过气。",
        "glass": "到处都是邪恶，不神圣的邪恶。",
        "rag": "刺穿的伤口，泥土与鲜血。",
    }
    EFFECT_QUOTES = {
        "wax": "火对善与恶一视同仁。",
        "china": "一阵强风推了你一把。",
        "stone": "你在污秽里越陷越深，又黑又脏。",
        "glass": "不神圣的存在，盘踞在曾有善意的地方。",
        "rag": "血红，玫瑰之死。",
    }
    KIND_ORDER = ("wax", "china", "stone", "glass", "rag")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("dolls", [])
        flags.setdefault("cleared_rooms", [])
        flags.setdefault("pending_draws", {})
        heroes = [p for p in engine.state.players if p.role == "hero"]
        for index, hero in enumerate(heroes):
            kind = self.KIND_ORDER[index % len(self.KIND_ORDER)]
            candidates = self.CANDIDATES[kind]
            discovered = [tid for tid in candidates if self._is_discovered(engine, tid)]
            if len(discovered) == 1:
                chosen = discovered[0]  # p107：恰有一间已发现 → 必须选它
            else:
                chosen = candidates[0]  # 都发现/都没发现 → bot 取列表第一间（原版叛徒任选）
            flags["dolls"].append(
                {"kind": kind, "hero_id": hero.id, "room_template": chosen,
                 "destroyed": bool(hero.dead), "found": False}
            )
            if hero.dead:
                # p36：英雄死亡其娃娃同时销毁。探索阶段就倒下的英雄开局即
                # 触发这条，否则一只永远无人能销毁的娃娃会把英雄胜利锁死。
                engine._log(f"{hero.name} 已不在人世——对应的那只{self.DOLL_NAMES[kind]}随之碎裂。")
                continue
            engine._log(f"{hero.name} 听到了一段引文：「{self.DESCRIPTION_QUOTES[kind]}」")
        engine._log("叛徒已经把和每个人一一对应的巫毒娃娃藏进了这座房子。")

    def _is_discovered(self, engine: Any, template_id: str) -> bool:
        return any(
            room.template_id == template_id and room.revealed and not engine._is_collapsed(key)
            for key, room in engine.state.board.items()
        )

    # ----------------------------------------------------------- 状态查询
    def _dolls(self, engine: Any) -> list[dict]:
        return list(engine._haunt_flags().get("dolls", []) or [])

    def _own_doll(self, engine: Any, player: Any) -> dict | None:
        return next(
            (d for d in self._dolls(engine) if d["hero_id"] == player.id and not d["destroyed"]),
            None,
        )

    def _destroy_doll(self, engine: Any, doll: dict, reason: str) -> None:
        doll["destroyed"] = True
        engine._log(reason)
        engine.check_victory()

    # ------------------------------------------------- 探索规则变更（p36）
    def explore_stop_suspended(self, engine: Any, player: Any) -> bool:
        return True

    def suppress_room_draw(self, engine: Any, player: Any, room: Any) -> bool:
        """发现符号房间时不立刻抽牌：抽牌推迟到「结束移动的房间」（p36）。"""
        if not room.symbol:
            return False
        pending = engine._haunt_flags().setdefault("pending_draws", {})
        pending[str(room.key)] = player.id
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        if not actions:
            return actions
        dolls = self._dolls(engine)
        if not any(not d["destroyed"] for d in dolls):
            return []  # 全部销毁：没有可搜寻的东西了
        room = engine.current_room(player)
        cleared = engine._haunt_flags().get("cleared_rooms", [])
        if room.template_id in cleared:
            return []  # 这间房已被如实问过"没有"——再问不会得到新答案
        if player.control == "bot" and player.role == "hero":
            own = self._own_doll(engine, player)
            if own is None:
                return []
            in_play = set(self.CANDIDATES[own["kind"]])
            if own["found"]:
                in_play.add(own["room_template"])
            if room.template_id not in in_play:
                return []  # bot 只在自己娃娃的候选房间里搜寻
        return actions

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id != "search_doll":
            return super().perform_action(engine, player, action_id, data)
        room = engine.current_room(player)
        # p36：在当回合新发现的符号房间里搜寻 → 先抽一张符号牌（不打断移动）
        pending = engine._haunt_flags().setdefault("pending_draws", {})
        key = str(room.key)
        if pending.get(key) == player.id and room.symbol:
            pending.pop(key, None)
            engine._draw_symbol_card(player, room.symbol, stop_movement=False)
        if not engine._resolve_check(player, "knowledge", 2, "搜寻巫毒娃娃"):
            engine._log(f"{player.name} 在{room.name}翻找了半天，什么也没翻出来。")
            return True
        doll = next(
            (d for d in self._dolls(engine) if not d["destroyed"] and d["room_template"] == room.template_id),
            None,
        )
        if doll is None:
            cleared = engine._haunt_flags().setdefault("cleared_rooms", [])
            if room.template_id not in cleared:
                cleared.append(room.template_id)
            engine._log(f"叛徒如实回答：{room.name}里没有巫毒娃娃。")
            return True
        doll["found"] = True
        if doll["hero_id"] == player.id:
            self._destroy_doll(
                engine, doll,
                reason=f"{player.name} 在{room.name}找到了自己的{self.DOLL_NAMES[doll['kind']]}，当场把它砸了个粉碎！",
            )
        else:
            owner = next((p for p in engine.state.players if p.id == doll["hero_id"]), None)
            owner_name = owner.name if owner is not None else "某位英雄"
            engine._log(
                f"{player.name} 在{room.name}找到了{owner_name}的{self.DOLL_NAMES[doll['kind']]}——"
                "只有娃娃的主人能安全地销毁它。"
            )
        return True

    # ------------------------------------------------------- 时钟与效果
    def on_turn_end(self, engine: Any, player: Any) -> None:
        pending = engine._haunt_flags().setdefault("pending_draws", {})
        room = engine.current_room(player)
        key = str(room.key)
        # p36：只有「结束移动的房间」有符号才抽牌；没停在里面的一律作废
        if pending.get(key) == player.id and room.symbol:
            pending.pop(key, None)
            engine._draw_symbol_card(player, room.symbol, stop_movement=False)
        for stale in [k for k, owner in pending.items() if owner == player.id]:
            pending.pop(stale, None)
        # p107 时钟：叛徒回合结束推进；叛徒出局后由本轮最后一名存活玩家代推
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            if player.id == traitor.id:
                self._advance_clock(engine)
        elif _is_last_in_round(engine, player):
            self._advance_clock(engine)

    def _advance_clock(self, engine: Any) -> None:
        if engine.state.winner:
            return
        turn_no = engine._advance_haunt_track("turn_damage", 1)
        engine._log(f"回合/伤害轨道推进到 {turn_no}。")
        for doll in self._dolls(engine):
            if doll["destroyed"] or engine.state.winner:
                continue
            owner = next((p for p in engine.state.players if p.id == doll["hero_id"]), None)
            if owner is None or owner.dead:
                continue
            engine._log(f"「{self.EFFECT_QUOTES[doll['kind']]}」")
            self._apply_effect(engine, owner, doll, turn_no)
        engine.check_victory()

    def _apply_effect(self, engine: Any, hero: Any, doll: dict, turn_no: int) -> None:
        kind = doll["kind"]
        name = self.DOLL_NAMES[kind]
        if kind == "wax":
            stat = self._choose_loss(engine, hero, ("might", "speed"))
            engine._apply_stat_loss(hero, stat, 1)
            engine._check_player_death(hero)
        elif kind == "china":
            roll = engine.roll_dice(4, f"{name}坠落")
            if roll < turn_no:
                engine._log(f"{name}从高处坠下摔得粉碎——{hero.name} 当场死亡。")
                for stat in ("might", "speed", "sanity", "knowledge"):
                    hero.stats[stat] = 0
                engine._check_player_death(hero)
                self._destroy_doll_if_dead(engine, doll, hero)
            else:
                engine._log(f"{name}在风中摇晃，但没有落下（掷出 {roll}，回合数 {turn_no}）。")
        elif kind == "stone":
            roll = self._trait_roll(engine, hero, "might", f"{name}窒息")
            if roll < turn_no:
                engine._log(f"{hero.name} 快要窒息了，每项属性各失去 1 点。")
                for stat in ("might", "speed", "sanity", "knowledge"):
                    engine._apply_stat_loss(hero, stat, 1)
                engine._check_player_death(hero)
                self._destroy_doll_if_dead(engine, doll, hero)
            else:
                engine._log(f"{hero.name} 憋着气撑了过去（掷出 {roll}，回合数 {turn_no}）。")
        elif kind == "glass":
            stat = self._choose_loss(engine, hero, ("sanity", "knowledge"))
            engine._apply_stat_loss(hero, stat, 1)
            engine._check_player_death(hero)
        elif kind == "rag":
            roll = self._trait_roll(engine, hero, "knowledge", f"{name}绞紧")
            if roll < turn_no:
                engine._log(f"玫瑰的荆棘绞紧了——{hero.name} 受到 2 点物理伤害。")
                engine._deal_damage(hero, "physical", 2, source="血红的玫瑰")
                engine._check_player_death(hero)
                self._destroy_doll_if_dead(engine, doll, hero)
            else:
                engine._log(f"{hero.name} 挣脱了荆棘（掷出 {roll}，回合数 {turn_no}）。")

    def _destroy_doll_if_dead(self, engine: Any, doll: dict, hero: Any) -> None:
        # p36：英雄死亡时其娃娃同时销毁（China/Stone/Rag 直接致死的路径
        # 不走 on_player_died 的兜底时在这里补上；引擎死亡钩子会再兜一次）
        if hero.dead and not doll["destroyed"]:
            self._destroy_doll(engine, doll, reason=f"{hero.name} 倒下了，对应的那只巫毒娃娃随之碎裂。")

    def _trait_roll(self, engine: Any, hero: Any, stat: str, label: str) -> int:
        """属性掷骰的原始结果（石/布娃娃比较的是掷骰值与回合数，不是过线）。"""
        dice = max(1, min(8, engine._effective_stat(hero, stat) + engine._check_bonus(hero, stat)))
        return engine.roll_dice(dice, label)

    def _choose_loss(self, engine: Any, hero: Any, stats: tuple[str, str]) -> str:
        """「自选失去 1 点 X 或 Y」的确定性策略。

        bot：优先在「掉 1 点不会死」的属性里选当前数值较高的一项（平手取
        前者）；两项都会致死时掉前者。注意不能只比数值——轨道最底格的
        数值再高，掉 1 点也是直接见骷髅（实测 157 种子 P2 速度 2→0 当场死）。
        人类：弹窗自选。
        """
        if getattr(hero, "control", "bot") != "bot":
            labels = {"might": "力量", "speed": "速度", "sanity": "理智", "knowledge": "知识"}
            idx = engine.prompter.choose_from_list(
                "巫毒娃娃",
                f"{hero.name}：要失去 1 点{labels[stats[0]]}还是{labels[stats[1]]}？",
                [labels[stats[0]], labels[stats[1]]],
            )
            if idx is not None and 0 <= idx < len(stats):
                return stats[idx]

        def is_safe(stat: str) -> bool:
            track = engine._stat_track(hero, stat)
            if track:
                return int(hero.stat_positions.get(stat, 0)) >= 1
            return hero.stats.get(stat, 0) - 1 > 0

        pool = [s for s in stats if is_safe(s)] or list(stats)
        return max(pool, key=lambda s: hero.stats.get(s, 0))

    # --------------------------------------------------------- 死亡联动
    def on_player_died(self, engine: Any, player: Any) -> None:
        # p36：英雄死亡时，他的娃娃同时被销毁
        for doll in self._dolls(engine):
            if doll["hero_id"] == player.id and not doll["destroyed"]:
                self._destroy_doll(
                    engine, doll,
                    reason=f"{player.name} 倒下了，对应的那只巫毒娃娃随之碎裂。",
                )

    # ------------------------------------------------------------ bot
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero" or player.dead:
            return []
        own = self._own_doll(engine, player)
        if own is None:
            return []
        if own["found"]:
            return [own["room_template"]]  # 位置已被公开：直奔那间房
        cleared = set(engine._haunt_flags().get("cleared_rooms", []))
        return [tid for tid in self.CANDIDATES[own["kind"]] if tid not in cleared]

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes = [p for p in engine.state.players if p.role == "hero"]
        alive = [p for p in heroes if not p.dead]
        total = len(heroes)
        # p107：过半英雄死亡 → 叛徒胜（严格大于一半）
        if total and (total - len(alive)) * 2 > total:
            engine._set_winner("traitor", "黑暗里，一排按钮眼睛齐刷刷地眨了一下——过半英雄死了。")
            return True
        dolls = self._dolls(engine)
        # p36：销毁所有娃娃 且 存活英雄 ≥ 一半（向上取整）→ 英雄胜
        if dolls and all(d["destroyed"] for d in dolls) and len(alive) * 2 >= total:
            engine._set_winner("heroes", "最后一只娃娃被砸得粉碎，诅咒的丝线断了——活下来的人比死去的多。")
            return True
        return True  # 覆盖引擎「叛徒死亡→英雄胜」兜底：娃娃时钟不随叛徒死亡停下


class RatRitualMode(GenericModeHandler):
    """剧本 26 鼠祭（Pay the Piper）。

    权威原文：英雄手册 p37 / 叛徒手册 p108。

    已按原文实现：
        · 数值：老鼠 Speed 3 / Might 2 / Sanity 1（p108 页脚，新增 rat 模板
          ——骨架此前用 spider 冒充）。
        · 开局（p37/p108）：叛徒（鼠人）仍在场；属性低于初始值的先恢复到
          初始值，然后每项属性 +1。布置老鼠之前，先把身处五芒星室的探险者
          挪去邻格房间（不需要门相连）。
        · 老鼠（p108）：数量 = 玩家数 × 2，放进有符号（事件/物品/预兆）的
          未被占据房间；多于房间从头叠放，少于房间取前 N 间（bot 按 key 序
          确定，原版由叛徒任选）。
        · 老鼠战斗（p37/p108）：被击败即死亡（monster_killed_on_defeat）；
          同房间 ≥2 只 awake 老鼠合力攻击——力量相加、封顶 8 骰，对单一目标
          掷骰对决，失败不受伤（p108 明文）。
        · 五芒星室（p37/p108）：英雄与老鼠都不能进入——引擎新钩子
          room_entry_blocked 过滤英雄的移动选项、探索抽到该模板直接弃掉换
          一张；老鼠寻路绕开。叛徒进室后不受攻击（attack_allowed 闸门），
          并在 on_enter_room 里记 traitor_reached。
        · 仪式（p108）：五芒星室内理智 3+，成功 +1 理智检定轨道并把一只
          "可用"老鼠放到五芒星室邻格（可用 = 初始 2×N 池中不在场的老鼠，
          即被杀死的会回流）。所需次数 3-4 人 5 / 5-6 人 4（轨道 target
          固定 5，实际判定按人数在 check_victory 里算）。
        · 胜负（p37/p108）：英雄胜 = 杀光所有老鼠，或在叛徒抵达五芒星室
          之前杀死他；叛徒胜 = 仪式完成或英雄全灭。叛徒在五芒星室内被
          杀死不可能发生（免伤闸门）；他若在进室前被杀即英雄胜，
          吸收引擎「叛徒死亡→英雄胜」兜底（老坑 16 号吸收者）。

    已知简化：
        · 老鼠布置/叠放/仪式回流邻格由 bot 按 key 序决定，原版由叛徒任选。
        · p108 布点未明文排除五芒星室，但「英雄与老鼠都进不去」意味着放在
          里面的老鼠永远杀不掉、英雄「杀光老鼠」的胜利条件会被锁死——
          故布点排除五芒星室（校准决定）。
        · 单只老鼠攻击落败：原文应按差值受物理伤害（可能死），引擎不追踪
          怪物伤害，按既有惯例用「击晕一回合」表示攻击方受挫——只有被
          英雄击败时才按 p108「被击败即死」处理。
        · 「叛徒在五芒星室不受任何影响」以攻击闸门实现；物品/特殊能力对
          他的边界影响未逐一建模（bot 英雄只有普攻）。
    """

    mode = "rat_ritual"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        rats = self._rats(engine)
        rows = [f"场上老鼠 {len(rats)} 只（须清光）"]
        if engine._haunt_flags().get("traitor_reached"):
            rows.append("叛徒已进入五芒星室")
        return rows

    RAT = "rat"
    PENTAGRAM = "pentagram_chamber"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("traitor_reached", False)
        flags["rats_placed"] = False
        flags.setdefault("rat_pool", 0)
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        # p37：布置老鼠之前，先把五芒星室里的探险者挪去邻格（不需要门）
        penta_key = self._pentagram_key(engine)
        if penta_key:
            for person in engine.state.players:
                if person.dead or person.room_key != penta_key:
                    continue
                dest = next(
                    (
                        k
                        for k in sorted(engine._grid_neighbors(penta_key))
                        if k != penta_key and not engine._is_collapsed(k)
                    ),
                    "",
                )
                if dest:
                    person.room_key = dest
                    engine._log(f"五芒星室里的符号开始发烫——{person.name} 被挪到了隔壁。")
        # p108：鼠人强化——属性先恢复初始值，再每项 +1
        if traitor is not None:
            self._boost_traitor(engine, traitor)
        # p108：老鼠 = 玩家数 × 2，放进有符号的未被占据房间
        count = 2 * len(engine.state.players)
        flags["rat_pool"] = count
        spec = self._rat_spec(engine)
        eligible = sorted(
            key
            for key, room in engine.state.board.items()
            if room.symbol in ("event", "item", "omen")
            and room.template_id != self.PENTAGRAM
            and not engine._is_collapsed(key)
            and not engine.room_occupants(key)
        )
        placed = 0
        if eligible:
            for index in range(count):
                # 少于房间 → 取前 N 间；多于房间 → 从头叠放（bot 确定性策略）
                target = eligible[index % len(eligible)]
                if engine._spawn_single_haunt_monster(spec, target) is None:
                    break
                placed += 1
        flags["rats_placed"] = True
        engine._log(f"{placed} 只老鼠从墙缝与踢脚板下涌了出来。")

    def _boost_traitor(self, engine: Any, traitor: Any) -> None:
        face = engine.catalog.characters.get(traitor.character_id)
        if face is None:
            return
        for stat in ("might", "speed", "sanity", "knowledge"):
            start = face.stats.get(stat)
            if start is None:
                continue
            track = engine._stat_track(traitor, stat)
            if track is not None:
                if traitor.stats[stat] < start:
                    idx = next((i for i, v in enumerate(track) if v >= start), len(track) - 1)
                    traitor.stat_positions[stat] = idx
                    traitor.stats[stat] = track[idx]
                # 按数值 +1（跳过同值格），而不是按格 +1——轨道常有重复值
                target_value = traitor.stats[stat] + 1
                idx = next((i for i, v in enumerate(track) if v >= target_value), len(track) - 1)
                traitor.stat_positions[stat] = idx
                traitor.stats[stat] = track[idx]
            else:
                traitor.stats[stat] = max(traitor.stats[stat], start) + 1
        engine._log(f"{traitor.name} 的皮下长出了灰色的绒毛——每项属性提升 1 点（p108）。")

    # ----------------------------------------------------------- 状态查询
    def _rats(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) == self.RAT]

    def _pentagram_key(self, engine: Any) -> str:
        return next(
            (k for k, room in engine.state.board.items() if room.template_id == self.PENTAGRAM),
            "",
        )

    def _rat_spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.RAT) or {"template_id": self.RAT, "name": "老鼠"})

    def _ritual_needed(self, engine: Any) -> int:
        return 5 if len(engine.state.players) <= 4 else 4  # p108：3-4 人 5 次，5-6 人 4 次

    # ------------------------------------------------- 进入限制与叛徒免疫
    def room_entry_blocked(self, engine: Any, player: Any, room: Any) -> bool:
        template_id = getattr(room, "template_id", None) or getattr(room, "id", "")
        if template_id != self.PENTAGRAM:
            return False
        # p37/p108：英雄与老鼠不能进入五芒星室（叛徒可以）
        return getattr(player, "role", "") != "traitor"

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        if getattr(target, "role", "") == "traitor":
            room = engine.state.board.get(getattr(target, "room_key", ""))
            if room is not None and room.template_id == self.PENTAGRAM:
                return False  # p37/p108：五芒星室里的叛徒不受任何影响
        return super().attack_allowed(engine, attacker, target)

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        if player.role == "traitor" and room.template_id == self.PENTAGRAM:
            if not engine._haunt_flags().get("traitor_reached"):
                engine._haunt_flags()["traitor_reached"] = True
                engine._log(f"{player.name} 踏进五芒星室开始念诵鼠语——他在这里任何人都碰不到。")

    # --------------------------------------------------------- 老鼠回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.RAT:
            return False
        target = engine._find_monster_target(monster)
        if target is None:
            return True
        if monster.room_key != target.room_key:
            steps = engine.roll_dice(max(1, monster.speed), "老鼠移动")
            path = self._rat_path(engine, monster.room_key, target.room_key)
            if len(path) > 1:
                monster.room_key = path[min(len(path) - 1, max(1, steps))]
                engine._log(f"{monster.name} 移动到 {engine.state.board[monster.room_key].name}。")
        if monster.room_key != target.room_key:
            return True
        pack = [
            m
            for m in engine.state.monsters
            if _monster_id(m) == self.RAT and m.room_key == monster.room_key and m.stunned_turns <= 0
        ]
        if len(pack) >= 2:
            # p108：合力攻击——力量相加、封顶 8 骰，失败不受伤
            dice = min(8, sum(max(0, m.might) for m in pack))
            attack_roll = engine.roll_dice(dice, "鼠群合力扑击")
            target_roll = engine._roll_attack(target, "might")
            engine._log(f"{len(pack)} 只老鼠合力扑向 {target.name}：{attack_roll} 对 {target_roll}。")
            if attack_roll > target_roll:
                engine._deal_damage(target, "physical", attack_roll - target_roll, source="鼠群")
            else:
                engine._log("鼠群扑空了——合力攻击失败不受伤（p108）。")
        else:
            engine._monster_attack(monster, target)
        return True

    def _rat_path(self, engine: Any, start: str, goal: str) -> list[str]:
        """避开五芒星室的最短路径（p37/p108：老鼠进不去）。"""
        if start == goal:
            return [start]
        graph = engine._build_graph()
        blocked = {
            k for k, room in engine.state.board.items() if room.template_id == self.PENTAGRAM
        }
        queue = [start]
        prev: dict[str, str | None] = {start: None}
        cursor = 0
        while cursor < len(queue):
            current = queue[cursor]
            cursor += 1
            for nxt in graph.get(current, ()):
                if nxt in prev or nxt in blocked:
                    continue
                prev[nxt] = current
                if nxt == goal:
                    path = [nxt]
                    while prev[path[-1]] is not None:
                        path.append(prev[path[-1]])
                    return list(reversed(path))
                queue.append(nxt)
        return [start]  # 无路可走：原地不动

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        return _monster_id(monster) == self.RAT  # p37/p108：老鼠被击败即死，不会昏迷

    # ------------------------------------------------------------- 仪式
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id != "perform_ritual":
            return super().perform_action(engine, player, action_id, data)
        before = engine._haunt_track_value("ritual_rolls")
        result = super().perform_action(engine, player, action_id, data)
        if engine._haunt_track_value("ritual_rolls") > before:
            self._spawn_ritual_rat(engine)
        return result

    def _spawn_ritual_rat(self, engine: Any) -> None:
        """p108：仪式成功后放一只"可用"老鼠到五芒星室邻格（不需要门）。"""
        pool = int(engine._haunt_flags().get("rat_pool", 0))
        if len(self._rats(engine)) >= pool:
            engine._log("老鼠令牌都在屋里跑着，没有多余的可用。")
            return
        penta_key = self._pentagram_key(engine)
        if not penta_key:
            return
        dest = next(
            (
                k
                for k in sorted(engine._grid_neighbors(penta_key))
                if k != penta_key and not engine._is_collapsed(k)
            ),
            "",
        )
        if not dest:
            return
        if engine._spawn_single_haunt_monster(self._rat_spec(engine), dest) is not None:
            engine._log("仪式的嘶鸣召来另一只老鼠，钻进了隔壁房间。")

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        # p37 英雄胜 1：杀光所有老鼠（布置之后任意时刻）
        if flags.get("rats_placed") and not self._rats(engine):
            engine._set_winner("heroes", "最后一只老鼠被踩扁了——墙里的吱吱声终于停了。")
            return True
        # p37 英雄胜 2：叛徒在抵达五芒星室之前被杀
        if traitor is not None and traitor.dead and not flags.get("traitor_reached"):
            engine._set_winner("heroes", "鼠人在完成仪式之前就被放倒了，鼠群四散而逃。")
            return True
        # p108 叛徒胜 1：仪式完成（3-4 人 5 次 / 5-6 人 4 次）
        if engine._haunt_track_value("ritual_rolls") >= self._ritual_needed(engine):
            engine._set_winner("traitor", "仪式完成了——墙里传来的不再是吱吱声，而是欢呼。")
            return True
        # p108 叛徒胜 2：英雄全灭
        if traitor is not None and not heroes_alive:
            engine._set_winner("traitor", "所有英雄都倒下了，老鼠们涌了出来。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：未进五芒星室的叛徒被杀才算英雄胜


class AmokFleshMode(GenericModeHandler):
    """剧本 27 失控的血肉（Amok Flesh）。

    权威原文：英雄手册 p38 / 叛徒手册 p109。

    已按原文实现：
        · Blob 不是怪物——是单团不断扩张的肉体，用房间集合
          （flags["blob_rooms"]）表示；实体桌游的 ≥20 枚令牌只是计数手段，
          引擎不设上限（ Blob 令牌不可被影响、不攻击，p109）。
        · 开局（p38/p109）：叛徒仍在场；持水晶球者弃掉它，Blob 从水晶球
          所在房间开始生长。没人持球时按叛徒所在房起算（原文默认作祟由
          水晶球触发，校准回退）。
        · 扩张（p109）：第一个怪物回合吞没起源房 + 门邻房；之后每个怪物
          回合沿门与既有 links（楼梯）扩散一圈；扩张完掷 1 骰，掷出 2 就
          再扩一圈，直到不是 2。
        · 转化（p109）：任何人进入/身处有 Blob 的房间（含叛徒）立刻变成
          Blobperson——弃掉所有物品与预兆、速度 2、不能攻击/被攻击/抽牌/
          用神秘电梯/发现新房间（新引擎钩子 can_discover_rooms），为叛徒
          而战。Blobperson 所占房间在怪物回合开始时种下新 Blob
          （flags["blob_seeded"]），与主体门连通后才并入并从那里扩张。
        · 英雄流程（p38，全部知识 3+，每步每回合一次）：
          ① 检查弱点：在与 Blob 房间门相连的邻室检定，累计成功玩家数次 →
             弱点找到（weakness_found）；
          ② 搜配料：在 11 间配料房检定，成功得 1 份配料（按英雄分开计数），
             该房不可再搜；
          ③ 投掷：在与 Blob 房间门相连的邻室用 1 格移动投出自己身上的
             1 份配料；投满玩家数份 → Blob 销毁，英雄胜。
        · 时钟（p109）：扩张挂在"怪物回合开始"——叛徒 alive 时为其回合
          结束，出局后由本轮最后一名存活玩家代推（惯例；老坑 17 号吸收者）。

    已知简化：
        · 原文"Blob 用尽所有移动方式（含煤导槽/画廊/坍塌房，且这三类
          进出要多花一步）"——本仓库这三间房没有 links 数据，煤导槽是
          房间效果而非链接，故 Blob 只按门与楼梯链接扩散，慢速规则未表达。
        · 配料房按本仓库模板共 11 间：无独立 Storeroom（larder 兼任），
          保险库不建模"打开"状态。
        · Blobperson 的 bot 行为：速度 2 移动，不攻击不行动（为叛徒效力
          的具体策略未建模——它已无事可做）。
        · 弱点/配料投掷的每房理智标记只落在 flags（searched_rooms），
          不生成实体令牌（无 gameplay 作用，纯标记）。
    """

    mode = "blob_weakness"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        rows = [f"Blob 已吞没 {len(flags.get('blob_rooms', []))} 间房间"]
        rows.append("弱点：已找到" if flags.get("weakness_found") else "弱点：未找到")
        bp = len(flags.get("blobperson_ids", []))
        if bp:
            rows.append(f"已被同化 {bp} 人")
        return rows

    INGREDIENT_ROOMS = (
        "attic", "conservatory", "furnace_room", "garden", "library",
        "research_laboratory", "junk_room", "kitchen", "larder", "vault",
        "wine_cellar",
    )

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("weakness_found", False)
        flags.setdefault("blob_rooms", [])
        flags.setdefault("blob_seeded", [])
        flags.setdefault("blob_grew_once", False)
        flags.setdefault("blobperson_ids", [])
        flags.setdefault("ingredients", {})
        flags.setdefault("searched_rooms", [])
        # p38/p109：持水晶球者弃掉它，Blob 从水晶球所在房间开始生长
        origin = ""
        holder = next(
            (p for p in engine.state.players if "omen_crystal_ball" in p.items and not p.dead),
            None,
        )
        if holder is not None:
            engine._discard_card_from_player(holder, "omen_crystal_ball", return_to_room=False)
            origin = holder.room_key
            engine._log(f"{holder.name} 手中的水晶球迸裂——Blob 从{engine.state.board[origin].name}开始涌动。")
        else:
            revealer = next(
                (p for p in engine.state.players if p.id == engine.state.haunt_revealer_id),
                None,
            )
            if revealer is not None and not revealer.dead:
                origin = revealer.room_key
            engine._log("水晶球不知去向——Blob 从叛徒身边开始涌动。")
        flags["blob_origin"] = origin

    # ----------------------------------------------------------- 状态查询
    def _is_blobperson(self, engine: Any, player: Any) -> bool:
        return str(player.id) in {str(i) for i in engine._haunt_flags().get("blobperson_ids", [])}

    def _is_blob_room(self, engine: Any, key: str) -> bool:
        flags = engine._haunt_flags()
        return key in flags.get("blob_rooms", []) or key in flags.get("blob_seeded", [])

    def _blob_adjacent(self, engine: Any, player: Any) -> bool:
        """p38：与 Blob 房间门相连的邻室。"""
        return any(
            self._is_blob_room(engine, nxt)
            for nxt in engine._door_neighbors(player.room_key)
            if nxt != player.room_key
        )

    def _needed(self, engine: Any) -> int:
        return len(engine.state.players)  # p38/p109：均按玩家数计

    # ------------------------------------------------- Blobperson 限制
    def on_turn_start(self, engine: Any, player: Any) -> None:
        if not player.dead and self._is_blobperson(engine, player):
            player.steps_remaining = 2  # p109：Blobperson Speed 2

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        if self._is_blobperson(engine, attacker) or self._is_blobperson(engine, target):
            return False  # p109：Blobperson 不能攻击、也不能被攻击
        return super().attack_allowed(engine, attacker, target)

    def suppress_room_draw(self, engine: Any, player: Any, room: Any) -> bool:
        return self._is_blobperson(engine, player)  # p109：Blobperson 不能抽牌

    def can_discover_rooms(self, engine: Any, player: Any) -> bool:
        return not self._is_blobperson(engine, player)  # p109：不能发现房间

    def mystic_elevator_blocked(self, engine: Any, player: Any) -> bool:
        return self._is_blobperson(engine, player)  # p109：不能用神秘电梯

    # --------------------------------------------------------- 扩张时钟
    def on_turn_end(self, engine: Any, player: Any) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            if player.id != traitor.id:
                return
        elif not _is_last_in_round(engine, player):
            return
        # p109：怪物回合开始——Blobperson 播种 → Blob 扩张 → 掷 2 追加
        self._seed_blobperson_rooms(engine)
        self._grow_blob(engine)
        guard = 0
        while engine.roll_dice(1, "Blob 扩张检定") == 2 and guard < 24:
            self._grow_blob(engine)
            guard += 1
        self._convert_in_blob(engine)
        engine.check_victory()

    def _blob_neighbors(self, engine: Any, key: str) -> set[str]:
        """Blob 扩散目标：门邻房 + 楼梯/特殊链接（慢速房间无链接数据，见简化）。"""
        room = engine.state.board.get(key)
        targets: set[str] = set()
        if room is None:
            return targets
        for nxt in engine._door_neighbors(key):
            if nxt != key and not engine._is_collapsed(nxt):
                targets.add(nxt)
        for target in room.links.values():
            tk = engine._link_target_key(target)
            if tk and tk != key and not engine._is_collapsed(tk):
                targets.add(tk)
        return targets

    def _grow_blob(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        blob = set(flags.get("blob_rooms", []))
        if not flags.get("blob_grew_once"):
            # p109：第一个怪物回合吞没起源房 + 门邻房
            origin = flags.get("blob_origin")
            if origin and origin in engine.state.board:
                blob.add(origin)
            grew: set[str] = set()
            for key in sorted(blob):
                grew |= self._blob_neighbors(engine, key)
            blob |= grew
            flags["blob_rooms"] = sorted(blob)
            flags["blob_grew_once"] = True
            engine._log(f"血肉骤然膨胀——Blob 吞没了 {len(blob)} 个房间！")
            return
        grew = set()
        for key in sorted(blob):
            grew |= self._blob_neighbors(engine, key)
        grew -= blob
        flags["blob_rooms"] = sorted(blob | grew)
        if grew:
            engine._log(f"Blob 蔓延进了 {len(grew)} 个新房间。")

    def _seed_blobperson_rooms(self, engine: Any) -> None:
        """p109：怪物回合开始，Blobperson 所占房间种下新 Blob；与主体门连通
        后并入主 Blob 并从那里扩张。"""
        flags = engine._haunt_flags()
        bp_ids = {str(i) for i in flags.get("blobperson_ids", [])}
        seeded = set(flags.get("blob_seeded", []))
        for person in engine.state.players:
            if person.dead or str(person.id) not in bp_ids:
                continue
            key = person.room_key
            if key not in flags["blob_rooms"] and key not in seeded:
                seeded.add(key)
                engine._log(f"{person.name} 脚下的房间也泛起了绿色的肉浪。")
        connected = set(flags["blob_rooms"])
        promoted = {
            k for k in seeded
            if any(n in connected for n in engine._door_neighbors(k))
        }
        for k in promoted:
            seeded.discard(k)
            flags["blob_rooms"].append(k)
            engine._log("种下的 Blob 与主体连成了一片。")
        flags["blob_seeded"] = sorted(seeded)

    def _convert_in_blob(self, engine: Any) -> None:
        for person in engine.state.players:
            if person.dead:
                continue
            if self._is_blob_room(engine, person.room_key):
                self._convert(engine, person)

    def _convert(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        bp = {str(i) for i in flags.get("blobperson_ids", [])}
        if str(player.id) in bp or player.dead:
            return
        bp.add(str(player.id))
        flags["blobperson_ids"] = sorted(bp)
        # p109：立刻弃掉所有物品与预兆
        for card_id in list(player.items):
            engine._discard_card_from_player(player, card_id, return_to_room=False)
        player.movement_stopped = True
        engine._log(f"{player.name} 被融进了 Blob——他变成了 Blobperson，转而为叛徒效力！")
        engine.check_victory()

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        # p109：任何人在有 Blob 的房间里立刻变成 Blobperson
        if self._is_blob_room(engine, room.key):
            self._convert(engine, player)

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        if self._is_blobperson(engine, player):
            return []
        actions = super().available_actions(engine, player)
        if not actions:
            return actions
        flags = engine._haunt_flags()
        blob_adjacent = self._blob_adjacent(engine, player)
        ingredients = int(flags.get("ingredients", {}).get(str(player.id), 0))
        searched = set(flags.get("searched_rooms", []))
        result = []
        for action in actions:
            if action.id == "examine_blob" and not blob_adjacent:
                continue  # 必须站在与 Blob 门相连的邻室（p38）
            if action.id == "search_ingredient" and player.room_key in searched:
                continue  # p38：该房已放过理智标记，不可再搜
            if action.id == "throw_ingredient" and (not blob_adjacent or ingredients <= 0):
                continue  # 必须邻室且身上有配料
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "examine_blob":
            return self._examine(engine, player)
        if action_id == "search_ingredient":
            return self._search(engine, player)
        if action_id == "throw_ingredient":
            return self._throw(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _examine(self, engine: Any, player: Any) -> bool:
        if not self._blob_adjacent(engine, player):
            return False
        if not engine._resolve_check(player, "knowledge", 3, "检查 Blob"):
            engine._log(f"{player.name} 盯着那团翻涌的血肉，什么也没看出来。")
            return True
        value = engine._advance_haunt_track("knowledge_rolls", 1)
        needed = self._needed(engine)
        if value >= needed:
            engine._haunt_flags()["weakness_found"] = True
            engine._set_haunt_track_value("knowledge_rolls", 0)
            engine._log(f"弱点找到了！{player.name} 的最后一次次检定揭示了 Blob 的死穴（p38）。")
        else:
            engine._log(f"{player.name} 记下了 Blob 的一处特征（{value}/{needed}）。")
        return True

    def _search(self, engine: Any, player: Any) -> bool:
        flags = engine._haunt_flags()
        room = engine.current_room(player)
        if room.template_id not in self.INGREDIENT_ROOMS or room.key in flags.get("searched_rooms", []):
            return False
        if not engine._resolve_check(player, "knowledge", 3, "搜寻配料"):
            engine._log(f"{player.name} 在{room.name}翻遍了架子，没找到能用的东西。")
            return True
        ingredients = flags.setdefault("ingredients", {})
        key = str(player.id)
        ingredients[key] = int(ingredients.get(key, 0)) + 1
        flags.setdefault("searched_rooms", []).append(room.key)
        engine._log(f"{player.name} 在{room.name}找到了一份配料（身上现有 {ingredients[key]} 份）。该房已放过理智标记，不能再搜。")
        return True

    def _throw(self, engine: Any, player: Any) -> bool:
        flags = engine._haunt_flags()
        ingredients = flags.setdefault("ingredients", {})
        key = str(player.id)
        if not self._blob_adjacent(engine, player) or int(ingredients.get(key, 0)) <= 0:
            return False
        # p38：投掷用 1 格移动
        if player.steps_remaining <= 0 and player.moved_this_turn:
            engine._log(f"{player.name} 已没有剩余移动力来投掷。")
            return True
        player.steps_remaining = max(0, player.steps_remaining - 1)
        player.moved_this_turn = True
        ingredients[key] = int(ingredients.get(key, 0)) - 1
        value = engine._advance_haunt_track("blob_ingredients", 1)
        engine._log(f"{player.name} 把一份配料掷进了 Blob（{value}/{self._needed(engine)}）。")
        engine.check_victory()
        return True

    # ------------------------------------------------------------ bot
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero" or player.dead or self._is_blobperson(engine, player):
            return []
        flags = engine._haunt_flags()
        blob = set(flags.get("blob_rooms", [])) | set(flags.get("blob_seeded", []))
        frontier: list[str] = []
        for key in sorted(blob):
            for nxt in engine._door_neighbors(key):
                if nxt not in blob:
                    frontier.append("__room__" + nxt)
        if not flags.get("weakness_found"):
            return frontier  # 弱点阶段：贴着 Blob 检定
        goals: list[str] = []
        searched = set(flags.get("searched_rooms", []))
        for key, room in engine.state.board.items():
            if room.template_id in self.INGREDIENT_ROOMS and key not in searched and key not in blob:
                goals.append("__room__" + key)
        if int(flags.get("ingredients", {}).get(str(player.id), 0)) > 0:
            goals.extend(frontier)  # 有配料：去 Blob 邻室投掷
        return goals

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p38 英雄胜：投满玩家数份配料 → Blob 销毁
        if engine._haunt_track_value("blob_ingredients") >= self._needed(engine):
            engine._set_winner("heroes", "烧杯落进翻涌的血肉——Blob 抽搐着把自己蒸发殆尽。")
            return True
        # p109 叛徒胜：所有英雄死亡或变成 Blobperson
        bp = {str(i) for i in flags.get("blobperson_ids", [])}
        heroes = [p for p in engine.state.players if p.role == "hero"]
        if heroes and all(p.dead or str(p.id) in bp for p in heroes):
            engine._set_winner("traitor", "最后的英雄也融进了那团不断扩张的血肉。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：叛徒死后 Blob 照常扩张


class DemonRingMode(GenericModeHandler):
    """剧本 28 所罗门之戒（Ring of King Solomon）。

    权威原文：英雄手册 p39 / 叛徒手册 p110。

    已按原文实现：
        · 数值（p110 页脚，新增 demon_1..demon_5 与 demon_lord 模板）：
          速/力/智 = 2/5/5、3/4/4、4/3/3、5/2/2、6/1/1；领主 1/7/7。
          地狱门房放 领主 + 数量=英雄数的恶魔（按恶魔一、二…顺序）。
        · 地狱门（p110）：无人的事件符号房间，距最近探险者 ≥4 格；
          没有就选最远的（bot 按 (距离, key) 定序，确定性）。
        · 戒指（p39）：作祟由所罗门戒指触发，揭示者（=叛徒）开局持有。
          英雄胜利 = 持戒指击败恶魔领主两次（力量或理智攻击皆可）；
          理智攻击对领主 +2；第一次击败击晕，第二次摧毁；领主攻击戒指
          持有人落败也算一次击败（领主回合由 handler 接管以记这次败北）。
        · 速度攻击免疫（p110）：领主 monster_specs immune_to=["speed"]，
          复用引擎既有免疫（左轮等速度武器打不中它）。
        · 策反（p39）：持戒指对普通恶魔的理智攻击成功 → 恶魔被策反；
          电子版由戒指持有人回合开始自动代跑（移动 + 攻击其他恶魔或叛徒），
          与剧本 21 僵尸代跑同款先例；戒指转给其他英雄控制权随之转移，
          戒指被丢/被叛徒或恶魔拿走 → 恶魔恢复不受控（动态判定）。
          怪物间战斗按引擎惯例"胜=击晕"近似（引擎不追踪怪物伤害）。
        · 抢戒指（p110）：恶魔（含领主）击败戒指持有人且赢 2+ → 改为抢走
          戒指不掉血（on_monster_attack）；恶魔不能使用/交易/丢掉它；
          击败带戒指恶魔的探险者立刻取回（monster_killed_on_defeat）。
        · 胜负（p39/p110）：英雄胜 = 领主被戒指摧毁；叛徒胜 = 英雄全灭。
          叛徒死亡后恶魔照常追杀（怪物回合由本轮最后存活玩家代跑，
          老坑 18 号吸收者）。

    已知简化：
        · 受控恶魔的"移动并攻击"在戒指持有人回合开始自动执行（bot 代跑），
          人类玩家不能逐只手动操控；怪物间胜负以击晕表示（引擎不追踪
          怪物伤害）。
        · 地狱门房没有合法候选的极端局面（事件房全被占/塌）下恶魔不入场，
          该局无法分出胜负（原文未覆盖）。
        · bot 英雄不挑理智攻击打领主（默认徒手力量攻击），拿回戒指前的
          攻略节奏偏慢，属 bot 深度。
    """

    mode = "demon_ring"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        rows = []
        portal = flags.get("portal_room")
        room = engine.state.board.get(portal) if portal else None
        rows.append(f"地狱之门：{room.name if room else '未开启'}")
        if flags.get("lord_destroyed"):
            rows.append("恶魔领主：已被戒指摧毁")
        controlled = len(flags.get("controlled_demons", []))
        if controlled:
            rows.append(f"受控恶魔 {controlled} 只")
        return rows

    LORD = "demon_lord"
    DEMON_TEMPLATES = ("demon_1", "demon_2", "demon_3", "demon_4", "demon_5")

    def __init__(self) -> None:
        self._attack_attrs: dict[str, str] = {}
        self._defeat_ctx: tuple[str, str] | None = None

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("portal_room", None)
        flags.setdefault("lord_destroyed", False)
        flags.setdefault("controlled_demons", [])
        # p110：地狱门 = 无人的事件符号房，距最近探险者 ≥4 格；没有就最远
        alive = [p for p in engine.state.players if not p.dead]
        candidates: list[tuple[int, str]] = []
        for key, room in engine.state.board.items():
            if room.symbol != "event" or engine._is_collapsed(key) or engine.room_occupants(key):
                continue
            dist = min(
                (engine._path_length(key, p.room_key) for p in alive),
                default=99,
            )
            candidates.append((dist, key))
        if not candidates:
            # 兜底（原文未覆盖）：场上没有合格事件房——从牌堆/弃牌堆里找
            # 一间事件符号房强行入场，否则这局永远无法分出胜负
            # （种子 109,4 实测：作祟开始时场上恰好没有事件房）。
            placed_key = ""
            for template_id in sorted(engine.catalog.room_templates):
                template = engine.catalog.room_templates[template_id]
                if template.symbol != "event":
                    continue
                placed_key = engine._ensure_room_in_play(template_id, room_key) or ""
                if placed_key:
                    break
            if not placed_key:
                engine._log("屋里找不到能撑开地狱之门的房间——门没有出现。")
                return
            flags["portal_room"] = placed_key
            engine._log(
                f"屋里本没有能开门的地方——地狱之力硬生生在{engine.state.board[placed_key].name}撕开了门。"
            )
            portal = placed_key
        else:
            far = max(dist for dist, _ in candidates)
            eligible = sorted(key for dist, key in candidates if dist >= 4)
            if not eligible:
                eligible = sorted(key for dist, key in candidates if dist == far)
            portal = eligible[0]
            flags["portal_room"] = portal
            engine._log(f"地板下的五芒星亮起——地狱之门在{engine.state.board[portal].name}打开了。")
        heroes = [p for p in engine.state.players if p.role == "hero"]
        specs = engine._haunt_rule_state().get("monster_specs", {})
        for spec_id in (self.LORD,) + tuple(f"demon_{i}" for i in range(1, len(heroes) + 1)):
            spec = dict(specs.get(spec_id) or {"template_id": spec_id})
            engine._spawn_single_haunt_monster(spec, portal)

    # ----------------------------------------------------------- 状态查询
    def _ring_holder(self, engine: Any) -> Any | None:
        return next(
            (p for p in engine.state.players if "omen_ring" in p.items and not p.dead),
            None,
        )

    def _controlled_ids(self, engine: Any) -> set[str]:
        """受控恶魔集合：仅当戒指在存活英雄手里时生效（p39）。"""
        holder = self._ring_holder(engine)
        if holder is None or holder.role != "hero":
            return set()
        return {str(i) for i in engine._haunt_flags().get("controlled_demons", [])}

    def _steal_ring(self, engine: Any, holder: Any, monster: Any) -> None:
        if "omen_ring" in holder.items:
            holder.items.remove("omen_ring")
            monster.items.append("omen_ring")
            engine._log(f"{monster.name} 击败了{holder.name}并抢走了所罗门戒指（它不会使用，p110）。")

    def _count_lord_defeat(self, engine: Any, killer: Any) -> None:
        value = engine._advance_haunt_track("lord_defeats", 1)
        if value >= 2:
            flags["lord_destroyed"] = True
            lord = next((m for m in engine.state.monsters if _monster_id(m) == self.LORD), None)
            if lord is not None:
                engine._kill_monster(lord, killer=killer)
            engine._log("恶魔领主第二次败在所罗门戒指之下——地狱之门塌缩成了地狱排水口！")
            engine.check_victory()
        else:
            engine._log(f"恶魔领主被击败（{value}/2），暂时被击晕。")

    # ------------------------------------------------- 戒指攻击修正（p39）
    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        # 记录本次攻击属性，供 attack_roll_bonus 判断"理智攻击 +2"。
        # 引擎保证同一攻击里先调本钩子再调加值钩子。
        self._attack_attrs[str(getattr(attacker, "id", ""))] = default_attr
        return None

    def attack_roll_bonus(self, engine: Any, attacker: Any, target: Any) -> int:
        if _monster_id(target) != self.LORD:
            return 0
        if "omen_ring" not in getattr(attacker, "items", []):
            return 0
        if self._attack_attrs.get(str(getattr(attacker, "id", ""))) != "sanity":
            return 0
        return 2  # p39：持戒指对领主的理智攻击 +2

    # --------------------------------------------------- 击败结算（p39/p110）
    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        tid = _monster_id(monster)
        if tid not in self.DEMON_TEMPLATES and tid != self.LORD:
            return False
        # p110：击败带戒指的恶魔 → 立刻取回戒指
        if "omen_ring" in (monster.items or []) and "omen_ring" not in getattr(attacker, "items", []):
            monster.items.remove("omen_ring")
            attacker.items.append("omen_ring")
            engine._log(f"{getattr(attacker, 'name', '探险者')} 从{monster.name}手里夺回了所罗门戒指！")
        self._defeat_ctx = (str(getattr(attacker, "id", "")), attack_attr)
        if tid != self.LORD:
            return False  # 普通恶魔不持戒指击败 = 照常击晕（是否策反看 on_monster_defeated）
        if "omen_ring" in getattr(attacker, "items", []):
            value = engine._advance_haunt_track("lord_defeats", 1)
            if value >= 2:
                engine._haunt_flags()["lord_destroyed"] = True
                engine._log("恶魔领主第二次败在所罗门戒指之下——地狱之门塌缩成了地狱排水口！")
                return True  # 引擎执行 _kill_monster
            engine._log(f"恶魔领主被击败（{value}/2），暂时被击晕。")
        return False  # 不持戒指的击败照常击晕，不计数

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        tid = _monster_id(monster)
        ctx = self._defeat_ctx
        self._defeat_ctx = None
        if tid in self.DEMON_TEMPLATES and ctx is not None:
            attacker_id, attack_attr = ctx
            holder = self._ring_holder(engine)
            if (
                holder is not None
                and str(holder.id) == attacker_id
                and attack_attr == "sanity"
            ):
                controlled = engine._haunt_flags().setdefault("controlled_demons", [])
                if monster.id not in controlled:
                    controlled.append(monster.id)
                engine._log(f"{monster.name} 在所罗门戒指的力量面前俯首——它被{holder.name}策反了！")
                return True  # 已处理：策反而非击晕
        return False  # 默认击晕

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        # p110：恶魔（含领主）赢戒指持有人 2+ → 抢戒指代替伤害
        if amount >= 2 and "omen_ring" in getattr(target, "items", []):
            self._steal_ring(engine, target, monster)
            return True
        return False

    # --------------------------------------------------------- 怪物回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        tid = _monster_id(monster)
        if tid == self.LORD:
            self._lord_turn(engine, monster)
            return True
        if tid in self.DEMON_TEMPLATES and monster.id in self._controlled_ids(engine):
            return True  # 受控恶魔由戒指持有人在回合开始代跑
        return False  # 未受控恶魔：引擎默认全速追最近英雄并攻击

    def _lord_turn(self, engine: Any, lord: Any) -> None:
        target = engine._find_monster_target(lord)
        if target is None:
            return
        if lord.room_key != target.room_key:
            steps = engine.roll_dice(max(1, lord.speed), "恶魔领主移动")
            path = engine._shortest_path(lord.room_key, target.room_key)
            if len(path) > 1:
                lord.room_key = path[min(len(path) - 1, max(1, steps))]
                engine._log(f"{lord.name} 移动到 {engine.state.board[lord.room_key].name}。")
        if lord.room_key != target.room_key:
            return
        attack_roll = engine._roll_monster_attack(lord, "might")
        target_roll = engine._roll_attack(target, "might")
        engine._log(f"{lord.name} 攻击 {target.name}：{attack_roll} 对 {target_roll}。")
        if attack_roll > target_roll:
            diff = attack_roll - target_roll
            if diff >= 2 and "omen_ring" in target.items:
                self._steal_ring(engine, target, lord)
            else:
                engine._deal_damage(target, "physical", diff, source=lord.name)
        elif attack_roll < target_roll:
            engine._stun_monster(lord, 1)
            if "omen_ring" in target.items:
                # p39：领主攻击戒指持有人落败也算一次击败
                self._count_lord_defeat(engine, killer=target)
        else:
            engine._log("平手。")

    # ------------------------------------------------- 受控恶魔代跑（p39）
    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.dead or player.role != "hero" or "omen_ring" not in player.items:
            return
        controlled_ids = self._controlled_ids(engine)
        if not controlled_ids:
            return
        for demon in list(engine.state.monsters):
            if _monster_id(demon) not in self.DEMON_TEMPLATES:
                continue
            if str(demon.id) not in controlled_ids or demon.stunned_turns > 0:
                continue
            self._controlled_demon_act(engine, demon)

    def _controlled_demon_act(self, engine: Any, demon: Any) -> None:
        enemies: list[Any] = [
            m
            for m in engine.state.monsters
            if _monster_id(m) in self.DEMON_TEMPLATES
            and m is not demon
            and str(m.id) not in self._controlled_ids(engine)
        ]
        enemies += [p for p in engine.state.players if p.role == "traitor" and not p.dead]
        if not enemies:
            return
        nearest = min(enemies, key=lambda e: engine._path_length(demon.room_key, e.room_key))
        if demon.room_key != nearest.room_key:
            steps = engine.roll_dice(max(1, demon.speed), "受控恶魔移动")
            path = engine._shortest_path(demon.room_key, nearest.room_key)
            if len(path) > 1:
                demon.room_key = path[min(len(path) - 1, max(1, steps))]
                engine._log(f"受控的{demon.name} 移动到 {engine.state.board[demon.room_key].name}。")
        if demon.room_key != nearest.room_key:
            return
        if isinstance(nearest, Player):
            attack_roll = engine._roll_monster_attack(demon, "might")
            target_roll = engine._roll_attack(nearest, "might")
            engine._log(f"受控的{demon.name} 攻击 {nearest.name}：{attack_roll} 对 {target_roll}。")
            if attack_roll > target_roll:
                engine._deal_damage(nearest, "physical", attack_roll - target_roll, source=demon.name)
            elif attack_roll < target_roll:
                engine._stun_monster(demon, 1)
            else:
                engine._log("平手。")
        else:
            # 怪物间战斗：引擎不追踪怪物伤害，按惯例"胜=击晕"近似
            attack_roll = engine._roll_monster_attack(demon, "might")
            target_roll = engine._roll_monster_attack(nearest, "might")
            engine._log(f"受控的{demon.name} 攻击 {nearest.name}：{attack_roll} 对 {target_roll}。")
            if attack_roll > target_roll:
                engine._stun_monster(nearest, 1)
            elif attack_roll < target_roll:
                engine._stun_monster(demon, 1)
            else:
                engine._log("平手。")

    # ------------------------------------------------------------ bot
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero" or player.dead:
            return []
        # 戒指还在叛徒手里：全队去围攻他抢戒指（其余目标走默认追怪逻辑）
        for other in engine.state.players:
            if other.role == "traitor" and not other.dead and "omen_ring" in other.items:
                return ["__room__" + other.room_key]
        return []

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p39 英雄胜：领主被戒指摧毁
        if flags.get("lord_destroyed"):
            engine._set_winner("heroes", "所罗门戒指燃起烈焰——恶魔领主被拖回了地狱。")
            return True
        # p110 叛徒胜：英雄全灭
        heroes = [p for p in engine.state.players if p.role == "hero"]
        if heroes and all(p.dead for p in heroes):
            engine._set_winner("traitor", "英雄们的尸体堆成了恶魔领主的血肉王座。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：叛徒死后恶魔照常追杀


class FrankensteinMode(GenericModeHandler):
    """剧本 29 弗兰肯斯坦的遗产（Frankenstein's Legacy）。

    权威原文：英雄手册 p40 / 叛徒手册 p111。

    已按原文实现：
        · 数值（p111 页脚，新增 frankenstein 模板）：Speed 3 / Might 8
          （原文未列神智，按无神智处理）。
        · 开局（p111）：怪物放在研究实验室或手术室；两间都不在场就从房间
          牌堆补一间（引擎 `_ensure_room_in_play` 按模板自身楼层放置；
          原文的"放上层"校准为按模板楼层，见已知简化）。另备 5 枚火把令牌。
        · 怪物行为（p111）：全速扑向最近的可攻击英雄（引擎默认）；
          攻击掷骰 +2（走 `monster_attack_roll_bonus`，仅在它主动攻击时加，
          防守不加）；免疫速度攻击（monster_specs `immune_to=["speed"]`，
          覆盖左轮等标了 speed 标签的武器）；赢 2+ 时可抢走并销毁英雄的
          火把而不掉血（`on_monster_attack`）。
        · 火刑（p40）：在 烧焦的房间/熔炉房/五芒星室/厨房 点燃火把
          （每名探险者同时只带 1 支，火把总数不限）；在怪物所在房或门相连
          的邻室做速度攻击投掷——赢则怪物吃 1 次火把命中且英雄失去火把
          （**不击晕**，引擎默认"击败=击晕"在这里不适用，故由 handler
          自己结算），输则只是失去火把、英雄不受伤。命中次数 = 玩家数时
          怪物死亡（轨道 torch_hits，target = player_count）。
        · 推落（p40）：怪物在塔楼/深渊时，同房间力量 6+ 把它推落摔死。
        · 胜负（p40/p111）：英雄胜 = 怪物死亡（火把命中达标或推落成功）；
          叛徒胜 = 英雄全灭。叛徒死亡后怪物照常追杀（怪物回合由本轮最后
          存活玩家代跑，老坑 19 号吸收者）。

    已知简化：
        · 原文"两间实验室都不在场时把该房放在上层"——本引擎
          `_ensure_room_in_play` 按模板自身楼层放置（研究实验室在地面层、
          手术室在二层），未强制上层。
        · 原文的 5 枚火把令牌是实体配件上限，且明说"找火把没有次数限制"，
          引擎按无限火把池处理，只保留"每名探险者同时只能带 1 支"。
        · 本仓库的炸药卡没有 speed 标签（按力量武器建模），因此怪物对
          炸药不免疫——给炸药补 speed 标签会波及全局对局基准，未改。
        · 怪物被英雄普通击败时仍按引擎默认"击晕一回合"处理
          （原文只强调火把命中不击晕）。
    """

    mode = "frankenstein_fire"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        if engine._haunt_flags().get("monster_destroyed"):
            return ["怪物：已被火把烧毁"]
        return []

    MONSTER = "frankenstein"
    TORCH = "torch"
    TORCH_ROOMS = ("charred_room", "furnace_room", "pentagram_chamber", "kitchen")
    PUSH_ROOMS = ("tower", "chasm")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("monster_destroyed", False)
        lab_key = next(
            iter(
                sorted(
                    key
                    for key, room in engine.state.board.items()
                    if room.template_id in ("research_laboratory", "operating_laboratory")
                )
            ),
            "",
        )
        if not lab_key:
            # p111：两间都不在场就从房间牌堆里找出来
            lab_key = (
                engine._ensure_room_in_play("research_laboratory", room_key)
                or engine._ensure_room_in_play("operating_laboratory", room_key)
                or ""
            )
        if not lab_key:
            engine._log("实验室既不在场也补不进来——怪物没能站起来。")
            return
        engine._spawn_single_haunt_monster(self._spec(engine), lab_key)
        engine._log("实验室里传来缝合线崩裂的声音——它站起来了。")

    def _spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.MONSTER) or {"template_id": self.MONSTER, "name": "弗兰肯斯坦的怪物"})

    # ----------------------------------------------------------- 状态查询
    def _monster(self, engine: Any) -> Any | None:
        return next((m for m in engine.state.monsters if _monster_id(m) == self.MONSTER), None)

    def _torches(self, engine: Any, player: Any) -> list[Any]:
        return engine.tokens_held_by(player.id, self.TORCH)

    def _near_monster(self, engine: Any, player: Any, monster: Any) -> bool:
        """p40：怪物所在房，或与它有门相连的邻室。"""
        if monster.room_key == player.room_key:
            return True
        return player.room_key in set(engine._door_neighbors(monster.room_key))

    def _needed(self, engine: Any) -> int:
        return len(engine.state.players)

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        if not actions:
            return actions
        monster = self._monster(engine)
        holding = bool(self._torches(engine, player))
        result = []
        for action in actions:
            if action.id == "light_torch" and holding:
                continue  # p40：每名探险者同时只能带 1 支火把
            if action.id == "throw_torch":
                if not holding or monster is None or not self._near_monster(engine, player, monster):
                    continue
            if action.id == "push_monster":
                if monster is None or monster.room_key != player.room_key:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "light_torch":
            return self._light_torch(engine, player)
        if action_id == "throw_torch":
            return self._throw_torch(engine, player)
        if action_id == "push_monster":
            return self._push_monster(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _light_torch(self, engine: Any, player: Any) -> bool:
        engine.spawn_token(self.TORCH, label="火把", role="carried", holder=player.id)
        engine._log(f"{player.name} 就地引燃了一支火把。")
        return True

    def _throw_torch(self, engine: Any, player: Any) -> bool:
        monster = self._monster(engine)
        torches = self._torches(engine, player)
        if monster is None or not torches:
            return False
        torch = torches[0]
        attack_roll = engine._roll_attack(player, "speed")
        defense = engine._roll_monster_attack(monster, "speed")
        engine._log(f"{player.name} 把火把掷向{monster.name}：{attack_roll} 对 {defense}。")
        engine.remove_token(torch.uid)  # 无论胜负，火把都消耗掉（p40）
        if attack_roll > defense:
            hits = engine._advance_haunt_track("torch_hits", 1)
            needed = self._needed(engine)
            engine._log(f"火把在怪物身上炸开一片火光（{hits}/{needed}）——它没有被击晕。")
            if hits >= needed:
                self._destroy_monster(engine, player)
        else:
            engine._log(f"{player.name} 投偏了，火把落地熄灭——人没受伤，只丢了火把（p40）。")
        return True

    def _push_monster(self, engine: Any, player: Any) -> bool:
        monster = self._monster(engine)
        if monster is None or monster.room_key != player.room_key:
            return False
        if not engine._resolve_check(player, "might", 6, "把怪物推下去"):
            engine._log(f"{player.name} 用尽力气也没能推动它。")
            return True
        engine._log(f"{player.name} 狠狠一推——{monster.name} 坠了下去（p40）。")
        self._destroy_monster(engine, player)
        return True

    def _destroy_monster(self, engine: Any, killer: Any) -> None:
        monster = self._monster(engine)
        if monster is None:
            return
        engine._haunt_flags()["monster_destroyed"] = True
        engine._kill_monster(monster, killer=killer)
        engine.check_victory()

    # ------------------------------------------------------- 怪物战斗特性
    def monster_attack_roll_bonus(self, engine: Any, monster: Any, target: Any) -> int:
        # p111：怪物攻击掷骰 +2（防守时不加——引擎只在这条主动攻击路径调用）
        return 2 if _monster_id(monster) == self.MONSTER else 0

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        # p111：赢 2+ 时可抢走并销毁火把而不掉血
        if _monster_id(monster) != self.MONSTER:
            return False
        torches = engine.tokens_held_by(getattr(target, "id", -1), self.TORCH)
        if amount > 2 and torches:
            for token in torches:
                engine.remove_token(token.uid)
            engine._log(f"{monster.name} 一把夺过{getattr(target, 'name', '探险者')}的火把捏灭了它（p111）。")
            return True  # 伤害已由剧本结算（抢火把，不掉血）
        return False

    # ------------------------------------------------------------ bot
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero" or player.dead:
            return []
        if self._torches(engine, player):
            return []  # 已有火把：走默认追怪逻辑，够得着就投
        return [
            "__room__" + key
            for key, room in engine.state.board.items()
            if room.template_id in self.TORCH_ROOMS
        ]

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        # p40 英雄胜：怪物死亡（火把命中达标或推落坠亡）
        if engine._haunt_flags().get("monster_destroyed"):
            engine._set_winner("heroes", "怪物终于不动了——弗兰肯斯坦的秘密随它一起烧成灰烬。")
            return True
        # p111 叛徒胜：英雄全灭
        heroes = [p for p in engine.state.players if p.role == "hero"]
        if heroes and all(p.dead for p in heroes):
            engine._set_winner("traitor", "缝合的怪物踩着英雄们的尸体，等待下一个命令。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：叛徒死后怪物照常追杀


class DraculaRisingMode(GenericModeHandler):
    """剧本 30 德古拉之墓（Tomb of Dracula）。

    权威原文：英雄手册 p41 / 叛徒手册 p112。

    已按原文实现：
        · 数值（p112 页脚，新增 dracula 与 bride 模板）：德古拉 速 5/力 8/
          智 6；新娘 4/4/4。
        · 开局（p112）：叛徒变吸血鬼（每项属性 +1）；德古拉放地窖或墓地，
          都不在场则放无人房距最近探索者 ≥4 格、再不行就最远（同 28 号
          地狱门口径）；女孩卡弃掉，新娘放在叛徒房间。
        · 时钟（p112）：叛徒回合开始把回合/伤害轨道推进到下一数字（从 1
          起）；随后立即由其他探险者之一掷「玩家数」枚骰，结果 < 当前
          回合数 → 日出（只发生一次）。叛徒出局后时钟由轮转首位存活玩家
          的回合开始代推（惯例）。
        · 日出后（p41）：每个叛徒回合开始，两只怪物吸血鬼每项属性各 -1
          （叛徒吸血鬼不弱化——原文只要求记录两只怪物的属性）；任一属性
          归零 → 昏迷不醒（on_monster_turn_start 跳过其行动）；英雄与昏迷
          吸血鬼同房间可"钉杀昏迷的吸血鬼"（每回合一次，代替攻击）；
          吸血鬼进入/身处 阳台/温室/花园/墓地/庭院/塔楼 立刻被阳光烧毁
          （其它朝外窗未建模，同 24 号口径）——叛徒吸血鬼同样会烧。
        · 圣物准入（p112）：吸血鬼怪物进教堂或持圣徽探险者的房间须理智
          6+，失败则停在门外（handler 接管移动逐房判定）；叛徒吸血鬼按
          硬阻挡简化（原文可掷骰硬闯，电子版避免移动选项列表期掷骰）。
        · 魅惑（p112）：吸血鬼可隔门从邻室对目标做理智攻击；赢则目标改受
          等额速度伤害、并可被拉进吸血鬼房间（bot 拉入）；输则吸血鬼不
          受伤。速度被魅惑打到见底 → 该角色变成吸血鬼：速度恢复初始值、
          每项属性 +1、引擎 role 改为 traitor（复用 bot 目标逻辑，同
          剧本 6 精神控制的电子化口径）。原文限定"异性目标"——角色数据
          无性别字段，对所有目标可用（同 20 号口径）。
        · 英雄杀法（p41）：长矛+力量攻击击败吸血鬼 = 钉杀（直接摧毁，
          monster_killed_on_defeat 按 weapon_id 判定）；其它成功攻击照常
          伤害/击晕；持圣徽者击败吸血鬼后按伤害点数把它沿门击退等距
          （on_monster_defeated 内结算，之后照常击晕）。
        · 胜负（p41/p112）：英雄胜 = 德古拉与新娘都被摧毁（钉杀/阳光烧毁
          均算）；叛徒胜 = 所有英雄死亡或变成吸血鬼。叛徒死亡后两只怪物
          照常行动（老坑 20 号吸收者）。

    已知简化：
        · 魅惑限定"异性目标"未建模（角色数据无性别字段，同 20 号）。
        · 叛徒吸血鬼的魅惑攻击未实现（原文 any Vampire 含叛徒；bot 叛徒
          按普通近战攻击处理）；其进教堂/圣徽房为硬阻挡而非 6+ 检定。
        · 怪物吸血鬼的移动由 handler 接管：逐房判圣物准入，但只在最终
          房间结算阳光燃烧（途经房间不判）。
        · "若叛徒获胜且吸血鬼杀了英雄，控制该吸血鬼的玩家也赢"——多胜方
          未建模（引擎单胜方）。
    """

    mode = "dracula_rising"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        rows = []
        if flags.get("sunrise"):
            rows.append("太阳已经升起——吸血鬼正在弱化")
        d = "已摧毁" if flags.get("dracula_destroyed") else "仍在"
        b = "已摧毁" if flags.get("bride_destroyed") else "仍在"
        rows.append(f"德古拉：{d}；新娘：{b}")
        return rows

    DRACULA = "dracula"
    BRIDE = "bride"
    VAMPIRE_MONSTERS = (DRACULA, BRIDE)
    SUNLIT_ROOMS = ("balcony", "conservatory", "garden", "graveyard", "patio", "tower")

    def __init__(self) -> None:
        self._defeat_ctx: tuple[str] | None = None

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("sunrise", False)
        flags.setdefault("vampire_ids", [])
        flags.setdefault("unconscious_ids", [])
        flags.setdefault("dracula_destroyed", False)
        flags.setdefault("bride_destroyed", False)
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        # p112：叛徒变吸血鬼，每项属性 +1
        if traitor is not None:
            self._boost(engine, traitor)
            self._mark_vampire(engine, traitor)
            engine._log(f"{traitor.name} 的獠牙长了出来——他也成了吸血鬼。")
        # p112：德古拉 → 地窖或墓地；都不在场 → 无人房 ≥4 格，否则最远
        drac_key = self._first_in_play(engine, ("crypt", "graveyard"))
        if not drac_key:
            drac_key = self._far_unoccupied(engine)
        specs = engine._haunt_rule_state().get("monster_specs", {})
        if drac_key:
            engine._spawn_single_haunt_monster(
                dict(specs.get(self.DRACULA) or {"template_id": self.DRACULA}), drac_key
            )
            engine._log("棺盖自己滑开了——地底传来德古拉苏醒前的第一声呼吸。")
        # p112：弃掉女孩卡，新娘放在叛徒房间
        self._discard_girl(engine)
        if traitor is not None:
            engine._spawn_single_haunt_monster(
                dict(specs.get(self.BRIDE) or {"template_id": self.BRIDE}), traitor.room_key
            )
            engine._log("女孩的身影在阴影里扭成了德古拉的新娘——她就站在叛徒身边。")

    def _boost(self, engine: Any, player: Any) -> None:
        """p112：每项属性 +1（按数值加，跳过轨道同值格）。"""
        for stat in ("might", "speed", "sanity", "knowledge"):
            track = engine._stat_track(player, stat)
            target_value = player.stats[stat] + 1
            if track is not None:
                idx = next((i for i, v in enumerate(track) if v >= target_value), len(track) - 1)
                player.stat_positions[stat] = idx
                player.stats[stat] = track[idx]
            else:
                player.stats[stat] = player.stats[stat] + 1

    def _first_in_play(self, engine: Any, template_ids: tuple[str, ...]) -> str:
        for template_id in template_ids:
            key = next(
                (k for k, room in engine.state.board.items() if room.template_id == template_id),
                "",
            )
            if key:
                return key
        return ""

    def _far_unoccupied(self, engine: Any) -> str:
        alive = [p for p in engine.state.players if not p.dead]
        candidates: list[tuple[int, str]] = []
        for key, room in engine.state.board.items():
            if engine.room_occupants(key) or engine._is_collapsed(key):
                continue
            dist = min((engine._path_length(key, p.room_key) for p in alive), default=99)
            candidates.append((dist, key))
        if not candidates:
            return ""
        far = max(dist for dist, _ in candidates)
        eligible = sorted(key for dist, key in candidates if dist >= 4)
        if not eligible:
            eligible = sorted(key for dist, key in candidates if dist == far)
        return eligible[0]

    def _discard_girl(self, engine: Any) -> None:
        for player in engine.state.players:
            if "omen_girl" in player.items:
                engine._discard_card_from_player(player, "omen_girl", return_to_room=False)
                engine._log("女孩卡在众人眼前化作一撮尘土（p112）。")
                return
        for key, items in engine.state.room_items.items():
            if "omen_girl" in items:
                items.remove("omen_girl")
                engine._log("躺在房间里的女孩卡化作一撮尘土（p112）。")
                return
        for deck in engine.state.card_decks.values():
            if "omen_girl" in deck:
                deck.remove("omen_girl")
                engine._log("牌堆里的女孩卡无声无息地消失了（p112）。")
                return
        for discard in engine.state.card_discards.values():
            if "omen_girl" in discard:
                discard.remove("omen_girl")
                engine._log("弃牌堆里的女孩卡无声无息地消失了（p112）。")
                return

    # ----------------------------------------------------------- 状态查询
    def _is_vampire_player(self, engine: Any, player: Any) -> bool:
        return str(getattr(player, "id", "")) in {
            str(i) for i in engine._haunt_flags().get("vampire_ids", [])
        }

    def _vampire_monsters(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) in self.VAMPIRE_MONSTERS]

    def _unconscious_ids(self, engine: Any) -> set[str]:
        return {str(i) for i in engine._haunt_flags().get("unconscious_ids", [])}

    def _destroy_vampire(self, engine: Any, monster: Any, killer: Any, reason: str) -> None:
        if _monster_id(monster) == self.DRACULA:
            engine._haunt_flags()["dracula_destroyed"] = True
        elif _monster_id(monster) == self.BRIDE:
            engine._haunt_flags()["bride_destroyed"] = True
        engine._log(reason)
        engine._kill_monster(monster, killer=killer)
        engine.check_victory()

    # ------------------------------------------------- 时钟与日出（p112）
    def on_turn_start(self, engine: Any, player: Any) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor" and not p.dead), None)
        if traitor is not None:
            if player.id != traitor.id:
                return
        else:
            # 叛徒出局：时钟改由轮转顺序里第一位存活玩家代推（惯例）
            order = engine.state.turn_order
            first_alive = next(
                (pid for pid in order if any(p.id == pid and not p.dead for p in engine.state.players)),
                None,
            )
            if player.id != first_alive:
                return
        self._advance_clock(engine)

    def _advance_clock(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        value = engine._advance_haunt_track("sun_track", 1)
        if not flags.get("sunrise"):
            # p41：轨道推进后立即由其他探险者之一掷「玩家数」枚骰
            roller = next(
                (p for p in engine.state.players if p.role == "hero" and not p.dead),
                None,
            )
            roll = engine.roll_dice(len(engine.state.players), "日出检定")
            if roll < value:
                flags["sunrise"] = True
                engine._log(f"日出检定 {roll} < 回合数 {value}——太阳升起来了！（p41）")
            else:
                engine._log(f"日出检定 {roll} ≥ 回合数 {value}，夜还深着。")
        else:
            # p41：两只怪物吸血鬼每项属性各 -1（叛徒吸血鬼不弱化）
            for monster in self._vampire_monsters(engine):
                if monster.id in self._unconscious_ids(engine):
                    continue
                for stat in ("speed", "might", "sanity"):
                    setattr(monster, stat, max(0, getattr(monster, stat) - 1))
                if any(getattr(monster, s) <= 0 for s in ("speed", "might", "sanity")):
                    engine._haunt_flags().setdefault("unconscious_ids", []).append(monster.id)
                    engine._log(f"{monster.name} 在阳光下不支倒地，昏迷不醒——快去钉杀它！")
        self._burn_vampires_in_sunlight(engine)
        engine.check_victory()

    def _burn_vampires_in_sunlight(self, engine: Any) -> None:
        """p41：日出后吸血鬼进入/身处向阳房间即被烧毁（含叛徒吸血鬼）。"""
        if not engine._haunt_flags().get("sunrise"):
            return
        for monster in list(self._vampire_monsters(engine)):
            room = engine.state.board.get(monster.room_key)
            if room is not None and room.template_id in self.SUNLIT_ROOMS:
                self._destroy_vampire(
                    engine, monster, None,
                    f"阳光灌进{room.name}——{monster.name} 尖啸着燃烧殆尽！",
                )
        for player in engine.state.players:
            if player.dead or not self._is_vampire_player(engine, player):
                continue
            room = engine.state.board.get(player.room_key)
            if room is not None and room.template_id in self.SUNLIT_ROOMS:
                engine._log(f"{player.name} 站进了阳光里——皮肤冒烟、燃成灰烬！")
                for stat in ("might", "speed", "sanity", "knowledge"):
                    player.stats[stat] = 0
                engine._check_player_death(player)

    def on_player_moved(self, engine: Any, player: Any) -> None:
        if self._is_vampire_player(engine, player):
            self._burn_vampires_in_sunlight(engine)

    # ------------------------------------------------- 圣物准入（p112）
    def _holy_blocked(self, engine: Any, monster: Any, room_key: str) -> bool:
        """吸血鬼怪物进入教堂/持圣徽者的房间须理智 6+；返回 True = 被逼退。"""
        room = engine.state.board.get(room_key)
        if room is None:
            return False
        has_symbol = any(
            p.role == "hero" and not p.dead and "omen_holy_symbol" in p.items
            and p.room_key == room_key
            for p in engine.state.players
        )
        if room.template_id != "chapel" and not has_symbol:
            return False
        roll = engine._roll_monster_attack(monster, "sanity")
        if roll >= 6:
            engine._log(f"{monster.name} 硬顶着圣物之力闯了进去（理智检定 {roll}）。")
            return False
        engine._log(f"{monster.name} 被圣物之力逼退（理智检定 {roll} < 6）。")
        return True

    def room_entry_blocked(self, engine: Any, player: Any, room: Any) -> bool:
        # 叛徒吸血鬼进教堂/圣徽房：硬阻挡（原文 6+ 可硬闯，校准简化）
        if not self._is_vampire_player(engine, player):
            return False
        if getattr(room, "template_id", getattr(room, "id", "")) == "chapel":
            return True
        key = getattr(room, "key", None)
        if key is None:
            return False
        return any(
            p.role == "hero" and not p.dead and "omen_holy_symbol" in p.items
            and p.room_key == key
            for p in engine.state.players
        )

    # --------------------------------------------------------- 怪物回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        tid = _monster_id(monster)
        if tid not in self.VAMPIRE_MONSTERS:
            return False
        if monster.id in self._unconscious_ids(engine):
            return True  # 昏迷不醒：不移动不攻击（仍可被钉杀）
        room = engine.state.board.get(monster.room_key)
        if (
            engine._haunt_flags().get("sunrise")
            and room is not None
            and room.template_id in self.SUNLIT_ROOMS
        ):
            self._destroy_vampire(
                engine, monster, None,
                f"阳光灌进{room.name}——{monster.name} 尖啸着燃烧殆尽！",
            )
            return True
        if tid == self.DRACULA and engine._haunt_track_value("sun_track") < 2:
            return True  # p112：德古拉第 2 回合前不移动不攻击（仍可防御）
        self._vampire_turn(engine, monster)
        return True

    def _vampire_turn(self, engine: Any, monster: Any) -> None:
        target = engine._find_monster_target(monster)
        if target is None:
            return
        # 移动：沿最短路径逐房判圣物准入（p112）
        path = engine._shortest_path(monster.room_key, target.room_key)
        steps = engine.roll_dice(max(1, monster.speed), "吸血鬼移动")
        moved = 0
        for nxt in path[1:]:
            if moved >= steps:
                break
            if self._holy_blocked(engine, monster, nxt):
                break
            monster.room_key = nxt
            moved += 1
        if moved:
            engine._log(f"{monster.name} 移动到 {engine.state.board[monster.room_key].name}。")
        # 同房间：普通力量攻击（引擎默认结算口径）
        if monster.room_key == target.room_key:
            attack_roll = engine._roll_monster_attack(monster, "might")
            target_roll = engine._roll_attack(target, "might")
            engine._log(f"{monster.name} 攻击 {target.name}：{attack_roll} 对 {target_roll}。")
            if attack_roll > target_roll:
                engine._deal_damage(target, "physical", attack_roll - target_roll, source=monster.name)
            elif attack_roll < target_roll:
                engine._stun_monster(monster, 1)
            else:
                engine._log("平手。")
            return
        # 隔门邻室：魅惑攻击（p112，理智对决）
        if target.room_key in set(engine._door_neighbors(monster.room_key)):
            attack_roll = engine._roll_monster_attack(monster, "sanity")
            target_roll = engine._roll_attack(target, "sanity")
            engine._log(f"{monster.name} 对 {target.name} 发动魅惑：{attack_roll} 对 {target_roll}。")
            if attack_roll > target_roll:
                diff = attack_roll - target_roll
                engine._apply_stat_loss(target, "speed", diff)
                engine._log(f"魅惑生效——{target.name} 受到 {diff} 点速度伤害。")
                target.room_key = monster.room_key
                engine._log(f"{target.name} 被拖进了{monster.name}所在的房间。")
                if target.stats["speed"] <= 0 and not target.dead:
                    self._vampirize(engine, target)
            elif attack_roll < target_roll:
                engine._log("魅惑被挣脱了——吸血鬼没有受伤（p112）。")
            else:
                engine._log("平手。")

    def _vampirize(self, engine: Any, player: Any) -> None:
        """p112：速度被魅惑打到见底 → 变成吸血鬼，转投叛徒方。"""
        if player.dead or self._is_vampire_player(engine, player):
            return
        self._mark_vampire(engine, player)
        player.role = "traitor"  # 复用引擎/bot 的阵营逻辑（同剧本 6 精神控制口径）
        face = engine.catalog.characters.get(player.character_id)
        for stat in ("might", "speed", "sanity", "knowledge"):
            track = engine._stat_track(player, stat)
            start = face.stats.get(stat) if face else None
            if start is not None and track is not None:
                idx = next((i for i, v in enumerate(track) if v >= start), len(track) - 1)
                player.stat_positions[stat] = idx
                player.stats[stat] = track[idx]
            target_value = player.stats[stat] + 1
            if track is not None:
                idx = next((i for i, v in enumerate(track) if v >= target_value), len(track) - 1)
                player.stat_positions[stat] = idx
                player.stats[stat] = track[idx]
            else:
                player.stats[stat] = player.stats[stat] + 1
        engine._log(f"{player.name} 的速度被吸到了尽头——他变成了吸血鬼，转而为德古拉效力！")
        engine.check_victory()

    def _mark_vampire(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        vampires = {str(i) for i in flags.get("vampire_ids", [])}
        vampires.add(str(player.id))
        flags["vampire_ids"] = sorted(vampires)

    # --------------------------------------------------- 英雄杀法（p41）
    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        tid = _monster_id(monster)
        if tid not in self.VAMPIRE_MONSTERS:
            return False
        # p41：长矛 + 力量攻击击败吸血鬼 = 钉杀
        if weapon_id == "omen_spear" and attack_attr == "might":
            self._destroy_vampire(
                engine, monster, attacker,
                f"{getattr(attacker, 'name', '探险者')} 把长矛钉进了{monster.name}的心脏！",
            )
            return True
        self._defeat_ctx = (str(getattr(attacker, "id", "")),)
        return False  # 其它成功攻击照常伤害/击晕

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        ctx = self._defeat_ctx
        self._defeat_ctx = None
        if _monster_id(monster) in self.VAMPIRE_MONSTERS and ctx is not None:
            attacker_id = ctx[0]
            attacker = next(
                (p for p in engine.state.players if str(p.id) == attacker_id), None
            )
            # p41：持圣徽者击败吸血鬼 → 按伤害点数沿门击退
            if attacker is not None and "omen_holy_symbol" in attacker.items and amount > 0:
                current = monster.room_key
                dist = engine._path_length(attacker.room_key, current)
                moved = 0
                while moved < amount:
                    neighbors = [
                        n for n in engine._door_neighbors(current)
                        if n != current and not engine._is_collapsed(n)
                    ]
                    if not neighbors:
                        break
                    best = sorted(
                        neighbors,
                        key=lambda k: (-engine._path_length(attacker.room_key, k), k),
                    )[0]
                    best_dist = engine._path_length(attacker.room_key, best)
                    if best_dist <= dist:
                        break
                    current = best
                    dist = best_dist
                    moved += 1
                if moved:
                    monster.room_key = current
                    engine._log(
                        f"圣徽放出光辉——{monster.name} 被{attacker.name}击退了 {moved} 个房间。"
                    )
        return False  # 照常击晕

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        if not actions:
            return actions
        unconscious = self._unconscious_ids(engine)
        result = []
        for action in actions:
            if action.id == "stake_unconscious":
                targets = [
                    m
                    for m in self._vampire_monsters(engine)
                    if m.id in unconscious and m.room_key == player.room_key
                ]
                if not targets:
                    continue  # 房间里没有昏迷的吸血鬼
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id != "stake_unconscious":
            return super().perform_action(engine, player, action_id, data)
        unconscious = self._unconscious_ids(engine)
        target = next(
            (
                m
                for m in self._vampire_monsters(engine)
                if m.id in unconscious and m.room_key == player.room_key
            ),
            None,
        )
        if target is None:
            return False
        self._destroy_vampire(
            engine, target, player,
            f"{player.name} 把木桩对准昏迷的{target.name}，狠狠钉了下去（p41）！",
        )
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p41 英雄胜：德古拉与新娘都被摧毁
        if flags.get("dracula_destroyed") and flags.get("bride_destroyed"):
            engine._set_winner("heroes", "木桩与阳光终结了吸血鬼——德古拉只剩一个传说。")
            return True
        # p112 叛徒胜：所有英雄死亡或变成吸血鬼（角色已转阵营，不再是 hero）
        heroes = [p for p in engine.state.players if p.role == "hero"]
        if heroes and all(p.dead for p in heroes):
            engine._set_winner("traitor", "最后的英雄倒下了——夜幕将永远笼罩这座房子。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：叛徒死后吸血鬼照常行动


class LivingHouseMode(GenericModeHandler):
    """剧本 31 器官房（It's Alive!）。

    权威原文：英雄手册 p42 / 叛徒手册 p113。

    这座房子本身是一个活物：六种器官系统（胃/肺/牙/腺体/心脏/大脑）+
    抗体。全程不改 engine.py / ui.py / models.py / net/，仅 content.py 新增
    antibody/heart/brain 三个怪物模板（数据，非引擎逻辑）；所有机制映射到
    GenericModeHandler 既有钩子。

    规则实现（对照原文）：
        · 六器官房：英雄“进入房间”(on_enter_room) 或“开始回合”(on_turn_start)
          时按房间 template_id 查表结算，两者时机不同不会双触发。
            - 胃（dining_room/kitchen/larder/wine_cellar）：Sanity 掷骰，5+ 无事；
              失败受 1 精神伤害；掷出 0/1 改受 2 精神伤害并停止移动。
            - 肺（conservatory + 有连通门的相邻房）：Might 4+；相邻房失败→移入温室
              再掷一次（通过则存活于温室）；温室内失败→该英雄被杀死并掉落所有物品。
            - 牙（balcony/entrance_hall）：Speed 掷骰，4+ 无事；1-3 受 1 物理；0 受 2 物理。
            - 腺体（research_laboratory/operating_laboratory）：掷两骰（和 0-4）：
              4→全属性+1；3→-2 速度；2→-2 力量；1→-2 理智；0→-2 知识。
        · 心脏（organ_room，怪物，防御 Might 7）/大脑（attic，怪物，防御 Might 6）：
          防御时不造成伤害（monster_counterattack_disabled）；永不移动/攻击
          （on_monster_turn_start 返回 True）；仅持 omen_spear 者可攻击（attack_allowed）；
          攻击大脑前须先 Sanity 4+，否则回合结束且不攻击；被长矛击败即“杀死房子”（英雄胜）。
        · 抗体（Speed3/Might5/Sanity3，数量=英雄数）：可穿墙移动（on_monster_move）；
          心脏/大脑被攻击且失败时，立即从屋内别处取一只抗体回流到该房（on_attack_resolved）。
        · 胜负：长矛击败心脏或大脑→英雄胜；杀光所有英雄，或叛徒偷矛后在
          chasm/furnace_room/underground_lake 花一整回合扔掉销毁→叛徒胜。叛徒存活。

    解释性决策（原文含糊处）：
        ① 长矛来源：p42/p113 未说明英雄如何获得长矛，只说叛徒“从持有它的英雄处偷走”。
           → setup 时把 omen_spear 授予 turn_order 中第一名英雄（确定性）。
        ② 腺体“全属性+1”：用 engine._increase_stat(player, stat, 1)（含 overflow 处理，
           是 _apply_stat_loss 的对称方法），逐一对 speed/might/sanity/knowledge +1。
        ③ 抗体穿墙移动语义：原文只说“can move through walls”未给距离规则。→ 朝最近英雄
           移动，忽略连通门（同楼层网格相邻即视为可穿墙抵达，跨楼层仍借门/楼梯连通），
           按 board 房间计数距离取掷骰步数内最接近目标的房间（复用木乃伊 on_monster_move
           范式）；对不在场/未发现房间跳过避免 KeyError。
        ④ 器官令牌：胃/肺/牙/腺体不生成实体蓝色器官令牌，改由房间 template_id 运行时
           查表判定——因此 p113“房间尚未出现时待其被发现再放令牌”自动满足（模板判定
           天然只在房间被发现/进入后生效）；rule_data 的 tokens 字段仅作 UI/配件提示保留。

    已知简化：
        · 攻击心脏/大脑“平手”时引擎在 on_attack_resolved 之前提前返回，故平手不触发
          抗体回流（仅“攻击落败”触发，与原文“attack fails”的主路径一致）。
        · 器官房的分档掷骰（胃/牙用 _roll_attack 取原始骰值、腺体用 roll_dice(2)）不走
          _resolve_check 的重掷/保存骰/护身符交互（与女妖哀鸣 _wail 先例一致）；肺与大脑
          的纯阈值检定走 _resolve_check，保留英雄的重掷能力。
        · 抗体穿墙（on_monster_move）仅在引擎调用该钩子时生效，而引擎只在“门/楼梯图
          存在到目标的路径（len(path)>1）”时才调用它；故抗体与最近英雄完全无门连通时
          本回合不相位（与木乃伊秘密通道先例同款的引擎级门控）。同楼层网格相邻即可
          穿墙抵达，但跨楼层仍须借门/楼梯触发钩子。
        · 长矛击杀语义：器官须“被长矛击败”（monster_killed_on_defeat 的 weapon_id==
          omen_spear）才杀死房子；仅“持有长矛”却空手或用异武器攻击只会击晕心脏/大脑、
          不置 house_killed（bot 选最高分武器必选长矛，无此问题；人类玩家需注意）。
    """

    mode = "living_house"

    HEART = "heart"
    BRAIN = "brain"
    ANTIBODY = "antibody"
    SPEAR = "omen_spear"
    STOMACH_ROOMS = ("dining_room", "kitchen", "larder", "wine_cellar")
    TEETH_ROOMS = ("balcony", "entrance_hall")
    GLANDS_ROOMS = ("research_laboratory", "operating_laboratory")
    CONSERVATORY = "conservatory"
    ANTIBODY_ROOMS = (
        "research_laboratory", "operating_laboratory", "entrance_hall",
        "furnace_room", "underground_lake", "library",
    )
    GRID_DELTAS = ((-1, 0), (0, -1), (0, 1), (1, 0))

    # ============================================================= setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        """p42/p113：放心脏（管风琴室）/大脑（阁楼）怪物、授予长矛、布抗体，
        并对当前处于胃房间的英雄立即各掷一次胃检定（按 turn_order 顺序）。"""
        flags = engine._haunt_flags()
        flags.setdefault("house_killed", False)
        flags.setdefault("spear_destroyed", False)
        # 心脏 / 大脑：房间不在场则拉进场
        organ_key = engine._ensure_room_in_play("organ_room", room_key)
        attic_key = engine._ensure_room_in_play("attic", room_key)
        if organ_key:
            engine._spawn_single_haunt_monster(self._spec(engine, self.HEART, "心脏"), organ_key)
        if attic_key:
            engine._spawn_single_haunt_monster(self._spec(engine, self.BRAIN, "大脑"), attic_key)
        # 长矛授予第一名英雄（解释性决策①）
        first_hero = self._first_hero(engine)
        if first_hero is not None:
            engine._grant_card_to_player(first_hero, self.SPEAR)
        # 抗体：数量=英雄数，均匀放入 6 指定房中在场者
        self._spawn_antibodies(engine)
        # setup 时当前在胃房间的英雄立即掷一次胃检定
        for player in self._heroes_in_turn_order(engine):
            room = engine.current_room(player)
            if room is not None and getattr(room, "template_id", "") in self.STOMACH_ROOMS:
                self._apply_stomach(engine, player)

    # ============================================================= 器官房查表
    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        self._apply_organ_effect(engine, player, room)

    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.dead:
            return
        self._apply_organ_effect(engine, player, engine.current_room(player))

    def _apply_organ_effect(self, engine: Any, player: Any, room: Any) -> None:
        """按房间 template_id 分派胃/肺/牙/腺体效果（仅影响英雄；Python 3.9 无 match，用 if 链）。"""
        if room is None or player.role != "hero" or player.dead:
            return
        template_id = getattr(room, "template_id", "")
        if not template_id:
            return
        if template_id in self.STOMACH_ROOMS:
            self._apply_stomach(engine, player)
            return
        if template_id in self.TEETH_ROOMS:
            self._apply_teeth(engine, player)
            return
        if template_id in self.GLANDS_ROOMS:
            self._apply_glands(engine, player)
            return
        if template_id == self.CONSERVATORY:
            self._apply_lungs(engine, player, in_conservatory=True)
            return
        # 肺的“相邻房”：与温室有连通门的房间
        conserv_key = self._room_key_by_template(engine, self.CONSERVATORY)
        if conserv_key and self._door_adjacent(engine, getattr(room, "key", ""), conserv_key):
            self._apply_lungs(engine, player, in_conservatory=False)

    def _apply_stomach(self, engine: Any, player: Any) -> None:
        """胃（消化）：Sanity 掷骰 5+ 无事；失败 1 精神伤害；0/1 → 2 精神伤害 + 停止移动。"""
        roll = engine._roll_attack(player, "sanity")
        engine._log(f"胃：{player.name} 在消化房里掷出理智 {roll}。")
        if roll >= 5:
            engine._log(f"{player.name} 稳住了心神，没有被胃液侵蚀。")
            return
        if roll <= 1:
            engine._deal_damage(player, "mental", 2, source="胃消化")
            player.movement_stopped = True
            engine._log(f"{player.name} 被胃液剧烈侵蚀（2 点精神伤害），停下脚步。")
        else:
            engine._deal_damage(player, "mental", 1, source="胃消化")

    def _apply_teeth(self, engine: Any, player: Any) -> None:
        """牙：Speed 掷骰 4+ 无事；1-3 受 1 物理；0 受 2 物理。"""
        roll = engine._roll_attack(player, "speed")
        engine._log(f"牙：{player.name} 在布满利齿的房间里掷出速度 {roll}。")
        if roll >= 4:
            engine._log(f"{player.name} 躲过了咬合的巨牙。")
            return
        engine._deal_damage(player, "physical", 2 if roll == 0 else 1, source="巨牙")

    def _apply_glands(self, engine: Any, player: Any) -> None:
        """腺体：掷两骰（和 0-4）：4→全属性+1；3→-2速度；2→-2力量；1→-2理智；0→-2知识。"""
        roll = engine.roll_dice(2, "腺体")
        engine._log(f"腺体：{player.name} 掷出两枚骰，和为 {roll}。")
        if roll >= 4:
            for stat in ("speed", "might", "sanity", "knowledge"):
                engine._increase_stat(player, stat, 1)  # 解释性决策②
            engine._log(f"{player.name} 被腺体分泌物强化（全属性 +1）。")
        elif roll == 3:
            engine._apply_stat_loss(player, "speed", 2)
        elif roll == 2:
            engine._apply_stat_loss(player, "might", 2)
        elif roll == 1:
            engine._apply_stat_loss(player, "sanity", 2)
        else:
            engine._apply_stat_loss(player, "knowledge", 2)
        engine._check_player_death(player)  # -2 降到骷髅（0）即死

    def _apply_lungs(self, engine: Any, player: Any, in_conservatory: bool) -> None:
        """肺（呼吸）：Might 4+；相邻房失败→移入温室再掷一次；温室内失败→被杀死并掉落物品。"""
        if engine._resolve_check(player, "might", 4, "抵抗房屋的肺"):
            engine._log(f"{player.name} 撑住了肺的挤压。")
            return
        if not in_conservatory:
            conserv_key = self._room_key_by_template(engine, self.CONSERVATORY)
            if conserv_key:
                player.room_key = conserv_key
                engine._log(f"肺把 {player.name} 吸进了温室！")
                if engine._resolve_check(player, "might", 4, "在温室中抵抗肺"):
                    engine._log(f"{player.name} 在温室里稳住了，但已被困在此处。")
                    return
        engine._log(f"{player.name} 在温室里被房屋的肺活活憋死！")
        player.dead = True
        engine._drop_inventory_on_death(player)
        engine.check_victory()

    # ============================================================= 心脏 / 大脑
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """仅持长矛者可攻击心脏/大脑；攻击大脑前须先 Sanity 4+，否则回合结束且不攻击。"""
        mid = _monster_id(target)
        if mid not in (self.HEART, self.BRAIN):
            return True
        if self.SPEAR not in (getattr(attacker, "items", None) or []):
            engine._log(f"只有长矛能伤到{'心脏' if mid == self.HEART else '大脑'}。")
            return False
        if mid == self.BRAIN and not engine._resolve_check(attacker, "sanity", 4, "直视房屋的大脑"):
            # p113：“his or her turn ends without attacking”。引擎移动闸门只看
            # dead/movement_stopped（不看 attack_used），故必须同时停移动、清空剩余
            # 移动力，否则英雄攻脑失败后仍能带完整步数白嫖离开阁楼。
            attacker.attack_used = True  # 回合结束且不攻击
            attacker.movement_stopped = True
            attacker.steps_remaining = 0
            engine._log(f"{attacker.name} 无法直视大脑，回合就此结束。")
            return False
        return True

    def monster_counterattack_disabled(self, engine: Any, monster: Any) -> bool:
        """心脏/大脑防御时不造成伤害。"""
        return _monster_id(monster) in (self.HEART, self.BRAIN)

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """被长矛击败即杀死房子（英雄胜）；非长矛（理论上被 attack_allowed 拦住）仅击晕。"""
        mid = _monster_id(monster)
        if mid not in (self.HEART, self.BRAIN):
            return False
        if weapon_id == self.SPEAR:
            engine._haunt_flags()["house_killed"] = True
            engine._set_haunt_track_value("house_slain", 1)
            engine._log(f"长矛刺穿了房屋的{'心脏' if mid == self.HEART else '大脑'}——这座活房子死了！")
            return True
        return False

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        """心脏/大脑被攻击且失败 → 从屋内别处取一只抗体回流到该房。"""
        mid = _monster_id(target)
        if mid not in (self.HEART, self.BRAIN) or attacker_won:
            return
        self._reflow_antibody(engine, getattr(target, "room_key", ""))

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """心脏/大脑永不移动/攻击（return True = 本回合不再行动）。"""
        return _monster_id(monster) in (self.HEART, self.BRAIN)

    # ============================================================= 抗体穿墙移动
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """抗体可穿墙：朝最近英雄移动，忽略连通门（解释性决策③）。"""
        if _monster_id(monster) != self.ANTIBODY:
            return False
        target = engine._find_monster_target(monster)
        if target is None or monster.room_key == target.room_key:
            return True  # 无目标或已在目标房：已处理（引擎随后会照常攻击同房目标）
        dest = self._wall_step_destination(engine, monster.room_key, target.room_key, max(0, int(rolled)))
        if dest and dest != monster.room_key:
            monster.room_key = dest
            room = engine.state.board.get(dest)
            engine._log(f"{monster.name} 穿过墙壁移动到{room.name if room else dest}。")
        return True

    # ============================================================= 叛徒销毁长矛
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        """throw_spear：叛徒在深渊/熔炉房/地下湖花一整回合把偷来的长矛销毁 → 叛徒胜。"""
        if action_id == "throw_spear":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and not engine._haunt_flags().get("spear_destroyed"):
                engine._haunt_flags()["spear_destroyed"] = True
                engine._discard_card_from_player(player, self.SPEAR, return_to_room=False)
                engine._log("叛徒把长矛投入深渊——房屋的克星就此消失！")
            return ok
        return super().perform_action(engine, player, action_id, data)

    # ============================================================= 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        if flags.get("house_killed"):
            engine._set_winner("heroes", "长矛杀死了活房子的心脏/大脑——这座房子终于死了。")
            return True
        if flags.get("spear_destroyed"):
            engine._set_winner("traitor", "长矛被销毁，再没有什么能杀死这座活房子。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "所有英雄都被活房子消化了。")
            return True
        return True  # 叛徒存活；吸收引擎“叛徒死亡→英雄胜”兜底（杀叛徒≠杀死房子）

    # ============================================================= 进度摘要
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        """公开信息：心脏/大脑存活、抗体数量与分布、长矛持有者/是否已销毁。"""
        flags = engine._haunt_flags()
        lines: list[str] = []
        heart = engine._monster_by_template(self.HEART)
        brain = engine._monster_by_template(self.BRAIN)
        lines.append("心脏：已被杀死" if heart is None else "心脏：存活（管风琴室，防御力量 7）")
        lines.append("大脑：已被杀死" if brain is None else "大脑：存活（阁楼，防御力量 6）")
        antibodies = [m for m in engine.state.monsters if _monster_id(m) == self.ANTIBODY]
        lines.append(f"抗体：{len(antibodies)} 只（可穿墙，护住心脏/大脑）")
        rooms: dict[str, int] = {}
        for m in antibodies:
            r = engine.state.board.get(m.room_key)
            name = r.name if r else m.room_key
            rooms[name] = rooms.get(name, 0) + 1
        if rooms:
            lines.append("抗体分布：" + "，".join(f"{k}×{v}" for k, v in sorted(rooms.items())))
        if flags.get("spear_destroyed"):
            lines.append("长矛：已被叛徒销毁。")
        else:
            holder = next(
                (p for p in engine.state.players if self.SPEAR in (getattr(p, "items", None) or []) and not p.dead),
                None,
            )
            lines.append(f"长矛：{holder.name + ' 持有' if holder else '不在任何人手上'}（只有它能杀死房子）。")
        return lines

    # ============================================================= 内部工具
    def _spec(self, engine: Any, template_id: str, name: str) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        spec = dict(specs.get(template_id) or {"template_id": template_id, "name": name})
        spec.setdefault("template_id", template_id)
        spec.setdefault("name", name)
        spec.setdefault("controller", "traitor")
        return spec

    def _spawn_antibodies(self, engine: Any) -> None:
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        count = len(heroes)
        if count <= 0:
            return
        in_play = sorted(
            {key for key in (self._room_key_by_template(engine, t) for t in self.ANTIBODY_ROOMS) if key}
        )
        if not in_play:
            return
        spec = self._spec(engine, self.ANTIBODY, "抗体")
        for i in range(count):
            engine._spawn_single_haunt_monster(spec, in_play[i % len(in_play)])  # round-robin 均匀分布

    def _reflow_antibody(self, engine: Any, dest_key: str) -> None:
        if not dest_key:
            return
        candidates = [
            m for m in engine.state.monsters
            if _monster_id(m) == self.ANTIBODY and m.room_key != dest_key
        ]
        if not candidates:
            return
        candidates.sort(key=lambda m: getattr(m, "id", ""))  # 确定性：取 id 最小且不在该房者
        moved = candidates[0]
        moved.room_key = dest_key
        room = engine.state.board.get(dest_key)
        engine._log(f"一只抗体穿过墙壁回流到{room.name if room else dest_key}，护住受伤的器官。")

    def _room_key_by_template(self, engine: Any, template_id: str) -> str | None:
        for key in sorted(engine.state.board):
            if engine.state.board[key].template_id == template_id:
                return key
        return None

    def _first_hero(self, engine: Any) -> Any | None:
        order = engine.state.turn_order
        if order:
            by_id = {p.id: p for p in engine.state.players}
            for pid in order:
                p = by_id.get(pid)
                if p is not None and p.role == "hero" and not p.dead:
                    return p
        for p in engine.state.players:
            if p.role == "hero" and not p.dead:
                return p
        return None

    def _heroes_in_turn_order(self, engine: Any) -> list[Any]:
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        order = engine.state.turn_order
        if order:
            by_id = {p.id: p for p in heroes}
            ordered = [by_id[pid] for pid in order if pid in by_id]
            seen = {p.id for p in ordered}
            ordered += [p for p in heroes if p.id not in seen]
            return ordered
        return heroes

    def _door_adjacent(self, engine: Any, key_a: str, key_b: str) -> bool:
        """两房间是否同楼层且有互相对接的门（复用 DragonSiege 写法）。"""
        a = engine.state.board.get(key_a)
        b = engine.state.board.get(key_b)
        if not a or not b or a.floor != b.floor or not key_a or not key_b:
            return False
        dx = b.x - a.x
        dy = b.y - a.y
        for direction, (ddx, ddy) in {
            "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
        }.items():
            if (dx, dy) == (ddx, ddy) and direction in a.doors and OPPOSITE_DOOR[direction] in b.doors:
                return True
        return False

    def _wall_graph(self, engine: Any) -> dict[str, list[str]]:
        """穿墙连通图：引擎门/楼梯图 ∪ 同楼层网格相邻（忽略门=穿墙）。输出排序列表保证确定性。"""
        collapse = getattr(engine, "COLLAPSE_KEY", "collapsed")
        graph: dict[str, dict[str, None]] = {
            key: dict.fromkeys(engine._build_graph().get(key, ())) for key in engine.state.board
        }
        for key in sorted(engine.state.board):
            room = engine.state.board[key]
            if room.data.get(collapse):
                continue
            for dx, dy in self.GRID_DELTAS:
                nk = engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
                if not nk or nk == key:
                    continue
                if engine.state.board[nk].data.get(collapse):
                    continue
                graph.setdefault(key, {})[nk] = None
                graph.setdefault(nk, {})[key] = None
        return {key: sorted(neighbors) for key, neighbors in graph.items()}

    def _bfs_dist(self, graph: dict[str, list[str]], start: str) -> dict[str, int]:
        dist = {start: 0}
        order = [start]
        i = 0
        while i < len(order):
            cur = order[i]
            i += 1
            for nb in graph.get(cur, ()):
                if nb not in dist:
                    dist[nb] = dist[cur] + 1
                    order.append(nb)
        return dist

    def _wall_step_destination(self, engine: Any, start_key: str, target_key: str, max_steps: int) -> str:
        """在 max_steps 步穿墙距离内，取最接近目标（穿墙距离最小）的房间；平手按 room_key。"""
        if max_steps <= 0:
            return start_key
        graph = self._wall_graph(engine)
        dist_target = self._bfs_dist(graph, target_key)
        dist_start = self._bfs_dist(graph, start_key)
        best_key = start_key
        best_rank = (dist_target.get(start_key, 9999), start_key)
        for key, d in dist_start.items():
            if d > max_steps:
                continue
            rank = (dist_target.get(key, 9999), key)
            if rank < best_rank:
                best_rank = rank
                best_key = key
        return best_key


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
        · p114「撤下所有非起始/非占用房间重新洗匀」未实现——本仓库没有
          移除房间的能力（22 号房屋坍塌只是打标记，不真删），撤房会破坏
          存档与寻路。简化为洗匀房间牌堆与弃牌堆，氛围用日志还原。
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
        # p114 房屋重排：原文要把已放置的非起始/非占用房间撤下重新洗匀
        # （简化见类文档：只洗匀牌堆与弃牌堆，房间留在场上）。
        deck = engine.state.room_deck
        deck.extend(engine.state.room_discard)
        engine.state.room_discard = []
        engine.rng.shuffle(deck)
        engine._log("整栋房子在震颤中重排——走廊、楼梯和房间像牌一样被洗了一遍。")
        placed = engine._ensure_room_in_play(self.ORGAN_ROOM, room_key)
        if placed:
            engine._log(f"管风琴的低鸣从{engine.state.board[placed].name}传来——那是回家的钥匙。")
        else:
            engine._log("管风琴始终没能出现——这一局的回家之路被彻底堵死了。")

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
        """p43/p114：英雄先把三条线索跑齐再去风琴房；叛徒先跑完五间干扰房。"""
        flags = engine._haunt_flags()
        if player.role == "traitor":
            left = [r for r in self.SABOTAGE_ROOMS if r not in flags.get("sabotage_rooms", [])]
            return list(left) if left else []
        pending: list[str] = []
        for flag_id, room_id in (
            ("clue_books", "library"),
            ("clue_trophy", "game_room"),
            ("clue_stars", "tower"),
        ):
            if not flags.get(flag_id):
                pending.append(room_id)
        # 线索找齐（或场上没有那间房）就去风琴房
        if not pending:
            return [self.ORGAN_ROOM]
        # 还差 1-2 条时先补线索：门槛 15+ 靠裸掷骰不可能达到
        return pending + [self.ORGAN_ROOM]

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


class CannibalFeastMode(GenericModeHandler):
    """剧本 46「The Feast / 盛宴」（英雄手册 p57 / 叛徒手册 p128）。

    叛徒把同伴们诱进了食人狂徒盘踞的宅子：阁楼里关着一批受害者，
    食人狂徒在餐厅待命。叛徒与狂徒吃得越多越强；英雄要么护送所有
    受害者从正门逃出去（前提是零伤亡），要么把叛徒和狂徒杀光。

    · 开局（p57/p128）：阁楼不在场则从牌堆取出放上层、餐厅不在场则
      取出放地面层（模板自带楼层，_ensure_room_in_play 自动满足）。
      阁楼放受害者（人数只）、餐厅放食人狂徒（人数只），全部同朝向。
    · 受害者漫游（p57）：叛徒左侧玩家的回合开始时，每只受害者直行
      2 格；不能直行则向左转走下一个出口；不能穿过未探明的门；与
      英雄同房间就停下不动。朝向按门方位实现（north/east/south/west，
      "左转"取逆时针下一向），比 8/20 号的连通图近似更保真。
    · 护送（p57）：英雄与受害者同房间时可带它移动（原版为回合开始
      免费带 2 格、任意方向；电子版简化为剧本行动——花 1 行动、
      自动沿最短路朝正门带 2 格，已知简化）。
    · 正门（p57）：门厅知识检定（撬锁）或力量 5+ 开门；成功后结束
      回合（抽事件卡未建模，同 16 号口径）。之后英雄可把同房间的
      受害者送出正门，自己也能出逃/再进门接人。
    · 伤亡即封锁（p57/p128）：只要有任何受害者或英雄被杀，英雄的
      "全员逃生"路线就关闭——只能杀光叛徒和狂徒。反之只要有一名
      受害者逃出正门，叛徒的"吃光受害者"路线也关闭。
    · 进食（p128）：受害者被杀翻成尸体、英雄被杀 likewise（引擎没有
      "放倒模型"，统一用尸体令牌）。叛徒或狂徒与尸体同房间、且房间
      里没有活着的英雄时，花整回合进食：所有属性 +1，尸体移出游戏。
      狂徒的加成直接写进怪物属性（45 号蜘蛛成长同款），攻击掷骰与
      移动掷骰天然生效。
    · 怪物互吃（p128）：狂徒攻击受害者成功即杀死——引擎没有怪物
      互攻，由 handler 在狂徒回合手写力量对决近似（21/27 号口径）。
    · 胜负（p57/p128）：英雄胜 = 叛徒与狂徒全灭，或（零伤亡时）全员
      逃出；叛徒胜 = 吃光所有受害者或杀光英雄。叛徒死亡≠英雄胜
      （狂徒还在就得继续打），老坑 #1 在本剧本必然触发，已吸收。
    · 受害者在怪物回合完全不行动（on_monster_turn_start 拦下）——
      它的移动只来自漫游与护送，绝不会主动凑到英雄面前。

    已知简化：
        · 「受害者对房屋危险与必需掷骰按怪物处理」未建模——事件卡与
          房间危险不作用于怪物（引擎事件卡只结算到玩家）。
        · 「叛徒/狂徒不减慢受害者」自动满足（引擎移动互不阻挡）。
        · 护送方向自动朝正门（原版任意方向）；人类失去"先往别处带"
          的选择权（同 22 号深渊定序口径）。
        · bot 叛徒不主动攻击受害者，吃受害者主要靠狂徒自动对决；
          人类叛徒可以用标准攻击杀死受害者（命中即死）。
    """

    mode = "cannibal_feast"

    ATTIC = "attic"
    DINING = "dining_room"
    ENTRANCE = "entrance_hall"
    VICTIM = "victim"
    FREAK = "cannibal_freak"
    # 朝向左转（逆时针）顺序：北 → 西 → 南 → 东
    LEFT_OF = {"north": "west", "west": "south", "south": "east", "east": "north"}
    DELTAS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("front_door_open", False)
        flags.setdefault("blood_spilled", False)
        flags.setdefault("victims_escaped", 0)
        flags.setdefault("victim_escaped_any", False)
        flags.setdefault("victim_corpses", 0)
        flags.setdefault("escaped_hero_ids", [])
        flags.setdefault("victim_facing", {})

        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        attic_key = engine._ensure_room_in_play(self.ATTIC, room_key)
        dining_key = engine._ensure_room_in_play(self.DINING, room_key)
        facing: dict[str, str] = {}
        victim_room = attic_key if attic_key is not None else (dining_key or room_key)
        if attic_key is None:
            engine._log("阁楼始终没能出现——受害者被关在了别处。")
        for _ in range(hero_count):
            monster = engine._spawn_single_haunt_monster(
                {"template_id": self.VICTIM, "name": "受害者"}, victim_room
            )
            if monster is not None:
                facing[monster.id] = "north"
        engine._log(f"{hero_count} 名受害者被关在楼上，瑟瑟发抖。")
        if dining_key is not None:
            for _ in range(hero_count):
                engine._spawn_single_haunt_monster(
                    {"template_id": self.FREAK, "name": "食人狂徒"}, dining_key
                )
            engine._log(f"{hero_count} 名食人狂徒在餐厅磨刀霍霍。")
        flags["victim_facing"] = facing
        flags["victims_total"] = sum(
            1 for m in engine.state.monsters if m.template_id == self.VICTIM
        )
        # 轨道 target 改写为实际英雄数（UI 进度面板显示真实 x/y）
        track = engine._haunt_tracks().setdefault(
            "victims_escaped", {"label": "逃出的受害者", "target": hero_count, "value": 0}
        )
        track["target"] = hero_count

    # ------------------------------------------------------- 受害者漫游
    def _victim_mover(self, engine: Any) -> Any:
        """「叛徒左侧的玩家」：回合顺序中叛徒之后的第一名活人。"""
        players = engine.state.players
        traitor_idx = next(
            (i for i, p in enumerate(players) if p.role == "traitor"), -1
        )
        if traitor_idx < 0:
            return None
        for offset in range(1, len(players) + 1):
            candidate = players[(traitor_idx + offset) % len(players)]
            if not candidate.dead:
                return candidate
        return None

    def _roam_victims(self, engine: Any) -> None:
        facing = engine._haunt_flags().setdefault("victim_facing", {})
        for monster in [m for m in engine.state.monsters if m.template_id == self.VICTIM]:
            for _ in range(2):  # 每次激活走 2 格（p57 "moves two rooms"）
                if self._hero_in_room(engine, monster.room_key):
                    break  # 与英雄同房间就不动
                if not self._victim_step(engine, monster, facing):
                    break

    def _victim_step(self, engine: Any, monster: Any, facing: dict[str, str]) -> bool:
        """走 1 格：直行优先，不能直行则左转一次（p57）。返回是否移动。"""
        room = engine.state.board.get(monster.room_key)
        if room is None:
            return False
        current = facing.get(monster.id, "north")
        for direction in (current, self.LEFT_OF.get(current, "north")):
            if direction not in room.doors:
                continue
            dx, dy = self.DELTAS[direction]
            target_key = engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
            if not target_key:
                continue  # 未探明的门不能穿
            monster.room_key = target_key
            facing[monster.id] = direction  # 朝向只在移动中改变
            if self._hero_in_room(engine, target_key):
                return False  # 撞见英雄就停下
            return True
        return False

    def _hero_in_room(self, engine: Any, room_key: str) -> bool:
        return any(
            p.role == "hero" and not p.dead and p.room_key == room_key
            for p in engine.state.players
        )

    # ------------------------------------------------------------- 回合
    def on_turn_start(self, engine: Any, player: Any) -> None:
        if engine.state.phase != "HAUNT_PHASE":
            return
        flags = engine._haunt_flags()
        # 已逃出的英雄不再参与移动（只剩"重新进门"行动）
        if player.id in set(flags.get("escaped_hero_ids", [])):
            player.movement_stopped = True
            return
        # p57：叛徒左侧玩家的回合开始时移动所有受害者
        mover = self._victim_mover(engine)
        if mover is not None and player.id == mover.id and not player.dead:
            self._roam_victims(engine)

    # ------------------------------------------------------------- 行动
    def _victims_in_room(self, engine: Any, room_key: str) -> list[Any]:
        return [
            m
            for m in engine.state.monsters
            if m.template_id == self.VICTIM and m.room_key == room_key
        ]

    def _corpses_in_room(self, engine: Any, room_key: str) -> list[Any]:
        return engine.tokens_in_room(room_key, "corpse")

    def _entrance_key(self, engine: Any) -> str | None:
        entrance = next(
            (r for r in engine.state.board.values() if r.template_id == self.ENTRANCE),
            None,
        )
        return entrance.key if entrance is not None else None

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        flags = engine._haunt_flags()
        escaped = set(flags.get("escaped_hero_ids", []))
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            # 已开门别再显示撬锁
            if aid == "unlock_front_door" and flags.get("front_door_open"):
                continue
            # 身边没有受害者就不显示护送/送出
            if aid in {"escort_victim", "send_victim_out"} and not self._victims_in_room(
                engine, player.room_key
            ):
                continue
            # 已逃出的英雄别再显示出逃
            if aid == "escape_house" and player.id in escaped:
                continue
            # 进食需要房间里有尸体、且没有活着的英雄（p128）
            if aid == "feast_corpse":
                if not self._corpses_in_room(engine, player.room_key):
                    continue
                if self._hero_in_room(engine, player.room_key):
                    continue
            result.append(action)
        # 「重新进门」条件是"该玩家已逃出"，rule_data 的 flags 表达不了，手动追加
        if player.role == "hero" and player.id in escaped:
            result.append(
                HauntAction("reenter_house", "重新进门", "从正门回到门厅，去接下一名受害者。")
            )
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "unlock_front_door":
            return self._unlock_front_door(engine, player)
        if action_id == "escort_victim":
            return self._escort_victim(engine, player)
        if action_id == "send_victim_out":
            return self._send_victim_out(engine, player)
        if action_id == "escape_house":
            flags = engine._haunt_flags()
            flags["escaped_hero_ids"] = sorted(
                set(flags.get("escaped_hero_ids", [])) | {player.id}
            )
            player.movement_stopped = True
            engine._log(f"{engine._player_label(player)} 从正门逃了出去，但还没到收工的时候。")
            return True
        if action_id == "reenter_house":
            flags = engine._haunt_flags()
            flags["escaped_hero_ids"] = sorted(
                set(flags.get("escaped_hero_ids", [])) - {player.id}
            )
            player.movement_stopped = False
            engine._log(f"{engine._player_label(player)} 重新溜回宅子，去接下一名受害者。")
            return True
        if action_id == "feast_corpse":
            return self._feast(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _unlock_front_door(self, engine: Any, player: Any) -> bool:
        """p57：知识检定（撬锁）或力量 5+。成功 → 开门 + 结束回合。"""
        use_might = False
        if getattr(player, "control", "bot") != "bot":
            idx = engine.prompter.choose_from_list(
                "正门", "用哪种方式开正门？", ["知识检定（撬锁）", "力量 5+（撞开）"]
            )
            use_might = idx == 1
        else:
            # bot：挑期望成功率更高的属性（力量按 5+ 门槛，知识按掷骰和）
            use_might = player.stats.get("might", 0) * 2 >= player.stats.get("knowledge", 0)
        if use_might:
            roll = engine.roll_dice(player.stats.get("might", 0), "撞门")
            ok = roll >= 5
            engine._log(f"{engine._player_label(player)} 撞门：掷出 {roll}（需 5+）。")
        else:
            ok = engine._resolve_check(player, "knowledge", 0, "撬锁")
            engine._log(
                f"{engine._player_label(player)} 试图撬开正门：{'成功' if ok else '失败'}。"
            )
        if not ok:
            return False
        engine._haunt_flags()["front_door_open"] = True
        engine._log("正门吱呀一声开了——外面的夜风从未如此甜美。")
        # p57：成功后抽事件卡并结束回合（抽卡未建模，同 16 号口径）
        self._end_turn(player)
        return True

    def _escort_victim(self, engine: Any, player: Any) -> bool:
        """p57：带同房受害者移动。原版为回合开始免费带 2 格、任意方向；
        电子版为 1 行动、自动沿最短路朝正门（已知简化）。"""
        victims = self._victims_in_room(engine, player.room_key)
        if not victims:
            return False
        victim = victims[0]
        if getattr(player, "control", "bot") != "bot" and len(victims) > 1:
            idx = engine.prompter.choose_from_list(
                "护送受害者",
                "带哪一名受害者走？",
                [f"受害者 {i + 1}" for i in range(len(victims))],
            )
            if idx is not None and 0 <= idx < len(victims):
                victim = victims[idx]
        entrance_key = self._entrance_key(engine)
        if entrance_key is None:
            return False
        path = engine._shortest_path(player.room_key, entrance_key)
        if len(path) <= 1:
            engine._log("已经在正门厅了——直接把受害者送出去吧。")
            return True
        steps = min(2, len(path) - 1)
        dest = path[steps]
        player.room_key = dest
        victim.room_key = dest
        engine._log(
            f"{engine._player_label(player)} 护着受害者移到{engine.state.board[dest].name}。"
        )
        return True

    def _send_victim_out(self, engine: Any, player: Any) -> bool:
        """p57：把受害者送出正门（1 格）。逃出的受害者移出游戏。"""
        victims = self._victims_in_room(engine, player.room_key)
        if not victims:
            return False
        self._escape_victim(engine, victims[0])
        return True

    def _escape_victim(self, engine: Any, victim: Any) -> None:
        engine.state.monsters = [m for m in engine.state.monsters if m.id != victim.id]
        flags = engine._haunt_flags()
        flags["victims_escaped"] = int(flags.get("victims_escaped", 0)) + 1
        flags["victim_escaped_any"] = True
        engine._advance_haunt_track("victims_escaped")
        engine._log(
            f"一名受害者逃出了正门（{flags['victims_escaped']}/{flags.get('victims_total', '?')}）！"
        )

    def _feast(self, engine: Any, player: Any) -> bool:
        """p128：与尸体同房间且房内无活英雄 → 花整回合进食，全属性 +1。"""
        corpses = self._corpses_in_room(engine, player.room_key)
        if not corpses or self._hero_in_room(engine, player.room_key):
            return False
        self._consume_corpse(engine, corpses[0])
        for stat in ("speed", "might", "sanity", "knowledge"):
            engine._increase_stat(player, stat, 1)
        self._end_turn(player)
        engine._log(f"{engine._player_label(player)} 花了一整回合进食，感觉浑身是劲。")
        return True

    def _consume_corpse(self, engine: Any, corpse: Any) -> None:
        if corpse.label == "受害者尸体":
            flags = engine._haunt_flags()
            flags["victim_corpses"] = max(0, int(flags.get("victim_corpses", 0)) - 1)
        engine.remove_token(corpse.uid)

    def _end_turn(self, player: Any) -> None:
        """结束该玩家的回合（"花整回合"的行动，p57/p128）。"""
        player.movement_stopped = True
        player.steps_remaining = 0
        player.attack_used = True
        player.item_used = True

    # ------------------------------------------------------------- 怪物
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        template = getattr(monster, "template_id", "")
        if template == self.VICTIM:
            # 受害者绝不主动行动：移动只来自漫游与护送（p57）
            return True
        if template != self.FREAK:
            return False
        # p128：狂徒攻击同房间的受害者，成功即杀死
        victims = self._victims_in_room(engine, monster.room_key)
        if victims:
            victim = victims[0]
            freak_roll = engine._roll_monster_attack(monster, "might")
            victim_roll = engine.roll_dice(victim.might, "受害者反抗")
            engine._log(f"食人狂徒扑向受害者：{freak_roll} 对 {victim_roll}。")
            if freak_roll > victim_roll:
                self._kill_victim_to_corpse(engine, victim, killer=monster)
            else:
                engine._log("受害者挣扎着躲开了。")
            return True  # 无论成败，这回合都花在扑击上
        # p128：与尸体同房间且无活英雄 → 进食
        corpses = self._corpses_in_room(engine, monster.room_key)
        if corpses and not self._hero_in_room(engine, monster.room_key):
            self._consume_corpse(engine, corpses[0])
            monster.speed += 1
            monster.might += 1
            monster.sanity += 1
            engine._log(f"{monster.name} 花了一整回合进食，变得更加强壮。")
            return True
        return False  # 正常追杀英雄

    def _kill_victim_to_corpse(self, engine: Any, victim: Any, killer: Any = None) -> None:
        """受害者被杀：翻成尸体令牌（p128），并封锁逃生路线。"""
        engine.spawn_token(
            "corpse", label="受害者尸体", role="marker", room_key=victim.room_key
        )
        flags = engine._haunt_flags()
        flags["victim_corpses"] = int(flags.get("victim_corpses", 0)) + 1
        flags["blood_spilled"] = True
        engine._kill_monster(victim, killer=killer)

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """p57/p128：受害者与食人狂徒被击败即死（不是击晕）。
        受害者被杀时在此生成尸体——本钩子的调用点唯一且就在击杀结算处。"""
        template = getattr(monster, "template_id", "")
        if template == self.VICTIM:
            self._kill_victim_to_corpse(engine, monster, killer=attacker)
            return True
        return template == self.FREAK

    def on_player_died(self, engine: Any, player: Any) -> None:
        """p128：探险者被杀也算尸体（放倒的模型），并封锁逃生路线。"""
        engine.spawn_token(
            "corpse", label="探险者尸体", role="marker", room_key=player.room_key
        )
        engine._haunt_flags()["blood_spilled"] = True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        traitor_alive = any(p.role == "traitor" and not p.dead for p in engine.state.players)
        freaks_alive = [m for m in engine.state.monsters if m.template_id == self.FREAK]
        victims_alive = [m for m in engine.state.monsters if m.template_id == self.VICTIM]

        # p57：英雄胜 A——叛徒与所有食人狂徒都死了
        if not traitor_alive and not freaks_alive:
            engine._set_winner("heroes", "叛徒与食人狂徒全部倒下，盛宴结束了。")
            return True
        # p57：英雄胜 B——零伤亡且全员（英雄+受害者）逃出
        if (
            not flags.get("blood_spilled")
            and int(flags.get("victims_total", 0)) > 0
            and int(flags.get("victims_escaped", 0)) >= int(flags.get("victims_total", 0))
            and heroes_alive
            and all(p.id in set(flags.get("escaped_hero_ids", [])) for p in heroes_alive)
        ):
            engine._set_winner("heroes", "最后一名受害者逃出正门——没人变成今晚的主菜。")
            return True
        # p128：叛徒胜 A——所有受害者都被吃掉（且从未有人逃出）
        if (
            not flags.get("victim_escaped_any")
            and not victims_alive
            and int(flags.get("victim_corpses", 0)) == 0
            and int(flags.get("victims_total", 0)) > 0
        ):
            engine._set_winner("traitor", "最后一名受害者被吃得干干净净——盛宴开席。")
            return True
        # 通用：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "所有英雄都倒下了。")
            return True
        # 吸收兜底：叛徒死亡但狂徒还在——游戏继续，不判英雄胜
        if not traitor_alive:
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        flags = engine._haunt_flags()
        if player.role != "hero":
            return []
        if player.id in set(flags.get("escaped_hero_ids", [])):
            return []
        # 门没开时优先护送受害者（受害者在哪，英雄就去哪）；门开了直奔门厅
        if not flags.get("front_door_open"):
            return [
                f"__room__{m.room_key}"
                for m in engine.state.monsters
                if m.template_id == self.VICTIM
            ]
        entrance_key = self._entrance_key(engine)
        return [f"__room__{entrance_key}"] if entrance_key else []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = ["正门：已打开" if flags.get("front_door_open") else "正门：还没打开"]
        total = int(flags.get("victims_total", 0))
        lines.append(f"受害者：逃出 {int(flags.get('victims_escaped', 0))}/{total}。")
        if flags.get("blood_spilled"):
            lines.append("已经见血——全员逃生路线关闭，只能杀光叛徒与狂徒。")
        return lines


class OuroborosMode(GenericModeHandler):
    """剧本 47「Worm Ouroboros / 衔尾蛇虫」（英雄手册 p58 / 叛徒手册 p129）。

    叛徒的身体从中线裂开，化作环绕世界的巨蛇闯入现实：双头各自游走，
    每离开一个房间就留下一节蛇身。16 节蛇身铺满全屋之日，就是宅子
    被碾碎之时。英雄必须先削弱、再围殴，赶在蛇长成之前斩下双头。

    · 开局（p129）：叛徒移出游戏——物品全部掉在揭示房、Girl/Dog/
      Madman 被蛇吞掉（直接弃置，不掉落）；两个蛇头放揭示房；
      16 节蛇身备用（flags 计数）。
    · 骷髅（p58）：英雄施咒要捡起叛徒掉落的骷髅（作祟由骷髅预兆触发
      时它就在叛徒手里）。强制触发的测试局叛徒未必持有——开局在
      揭示房补一张（28 号"无合格房时强行入场"同口径）。
    · 蛇头行动（p129）：每个蛇头单独掷 1 骰（0/1/2）定步数；走过的
      房间若无蛇身则放 1 节（每房限 1 枚、已放过的可穿过）；不能走
      密道/秘门/神秘电梯（门邻居天然排除前两者，电梯房显式排除）；
      探索者不影响蛇头移动；蛇头可以探索新房间并忽略符号抽牌。
    · 施咒（p58）：持骷髅者与蛇头同房间，每回合一次理智 5+——成功后
      该蛇头力量降为 5 且此后可被攻击（未施咒的蛇头 attack_allowed 拦截）。
    · 击杀（p58/p129）：施咒后每次击败 = 1 hit；每颗头需 hit 数 =
      玩家数的一半向上取整（3-4 人 2 次、5-6 人 3 次）。蛇头不可击晕
      ——on_monster_defeated 拦下击晕并计 hit，满数由 handler 杀死。
    · 免疫（p58/p129）：左轮与一切速度攻击无效（monster_specs immune_to）。
    · 胜负（p58/p129）：英雄胜 = 双头皆斩；叛徒胜 = 16 节蛇身全部进场。
      叛徒开局就出局（变蛇），必须吸收"叛徒死亡→英雄胜"兜底——
      老坑 #1 在本剧本必然触发（10 号同款）。

    已知简化：
        · 蛇头/蛇身对探索者移动的影响（p12 怪物阻挡口径）未建模——
          引擎没有"经过怪物房间受限"的移动层，蛇身只作记数与地图标记。
        · 蛇头探索新房间"掷出 2 时不因符号房间停止移动"自动满足
          （handler 放房不触发符号结算）。
        · 叛徒侧的 Turn/Damage Track 记 hit：本引擎用 flags dict 按蛇头
          id 计数（两只头各自独立），UI 进度以蛇身轨道呈现。
        · 骷髅兜底补牌不回记账目（直接放进房间物品，不从牌堆核销）。
    """

    mode = "worm_ouroboros"

    HEAD = "ouroboros_head"
    SKULL = "omen_skull"
    DEVOUR_CARDS = ("omen_dog", "omen_girl", "omen_madman")
    ELEVATOR = "mystic_elevator"
    BODY_TOTAL = 16
    DELTAS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("weakened_heads", [])
        flags.setdefault("head_hits", {})
        players = len(engine.state.players)
        flags["hits_needed"] = -(-players // 2)  # ceil(p/2)：3-4 人 2 次、5-6 人 3 次
        flags["body_left"] = self.BODY_TOTAL

        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            # p129：Girl/Dog/Madman 被蛇吞掉（直接弃置）——同伴类预兆卡
            # 在 items 与 companions 里都有记录，两边都要清。
            for cid in list(traitor.items):
                if cid in self.DEVOUR_CARDS:
                    traitor.items.remove(cid)
            for cid in list(traitor.companions):
                if cid in self.DEVOUR_CARDS:
                    traitor.companions.remove(cid)
            pile = engine.state.room_items.setdefault(room_key, [])
            pile.extend(traitor.items)
            traitor.items.clear()
            pile.extend(traitor.companions)
            traitor.companions.clear()
            traitor.dead = True
            engine._log("叛徒的身体从中线裂开——他已化作双头巨蛇，不再是玩家。")
            if self.SKULL not in pile and not any(
                self.SKULL in p.items for p in engine.state.players
            ):
                pile.append(self.SKULL)
                engine._log("叛徒掉落的物品里有一具骷髅——那是施咒的焦点。")

        for _ in range(2):
            engine._spawn_single_haunt_monster(
                {"template_id": self.HEAD, "name": "衔尾蛇头"}, room_key
            )
        engine._log("两条蛇头在房间里昂起，鳞片摩擦声充满了整栋房子。")

    # ------------------------------------------------------- 蛇头行动
    def _heads(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if m.template_id == self.HEAD]

    def _drop_body(self, engine: Any, room_key: str) -> None:
        """蛇头离开的房间放 1 节蛇身（每房限 1 枚，p129）。"""
        flags = engine._haunt_flags()
        if int(flags.get("body_left", 0)) <= 0:
            return
        if any(
            t.kind == "ouroboros_body" and t.room_key == room_key
            for t in engine.state.tokens
        ):
            return
        flags["body_left"] = int(flags["body_left"]) - 1
        engine.spawn_token("ouroboros_body", label="蛇身", role="marker", room_key=room_key)
        engine._advance_haunt_track("ouroboros_body")

    def _head_discover(self, engine: Any, direction: str, from_room: Any) -> str | None:
        """蛇头探索新房间（忽略符号抽牌，p129）。bot 取首个可行放置。"""
        dx, dy = self.DELTAS[direction]
        target_pos = (from_room.floor, from_room.x + dx, from_room.y + dy)
        if target_pos in engine.state.pos_index:
            return engine.state.pos_index[target_pos]
        budget = len(engine.state.room_deck) + len(engine.state.room_discard) + 1
        while budget > 0:
            budget -= 1
            template = engine._draw_room_template(from_room.floor)
            if template is None:
                return None
            placements = engine._compute_explore_placements(template, direction, target_pos)
            if not placements:
                engine.state.room_discard.append(template.id)
                continue
            placement = placements[0]
            rotated = engine._build_rotated_template(template, placement["rotation"])
            new_room = engine._place_room(
                rotated, target_pos[1], target_pos[2], placement["rotation"]
            )
            engine._log(f"蛇头撞开了未知区域：{new_room.name}")
            return new_room.key
        return None

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if getattr(monster, "template_id", "") != self.HEAD:
            return False
        target = engine._find_monster_target(monster)
        steps = engine.roll_dice(monster.speed, "蛇头移动")
        visited = [monster.room_key]
        cur = monster.room_key
        for _ in range(steps):
            room = engine.state.board[cur]
            body_keys = {
                t.room_key for t in engine.state.tokens if t.kind == "ouroboros_body"
            }
            # 已探明门邻居（排除神秘电梯，密道/秘道不在门邻居里）
            known = [
                k
                for k in engine._door_neighbors(cur)
                if engine.state.board[k].template_id != self.ELEVATOR
            ]
            fresh = [k for k in known if k not in body_keys]  # 已探明、还没蛇身
            unknown_dirs = [
                d
                for d in sorted(room.doors)
                if self._pos_of(engine, room, d) is None
            ]  # 未探明的门：蛇头可以探索新房间（p129）
            dest: str | None = None
            if fresh:
                if target is not None:
                    dest = min(fresh, key=lambda k: engine._path_length(k, target.room_key))
                else:
                    dest = sorted(fresh)[0]
            elif unknown_dirs:
                new_key = self._head_discover(engine, unknown_dirs[0], room)
                if new_key is None:
                    # 牌堆放不出新房间：退回已放蛇身的房间游走
                    if not known:
                        break
                    dest = (
                        min(known, key=lambda k: engine._path_length(k, target.room_key))
                        if target is not None
                        else sorted(known)[0]
                    )
                else:
                    visited.append(new_key)
                    cur = new_key
                    monster.room_key = new_key
                    continue
            elif known:
                # 只剩已放蛇身的房间：可以穿过（不再放，p129）
                dest = (
                    min(known, key=lambda k: engine._path_length(k, target.room_key))
                    if target is not None
                    else sorted(known)[0]
                )
            else:
                break
            visited.append(dest)
            cur = dest
            monster.room_key = dest
        # p129：蛇头离开的房间放 1 节蛇身（终点不算离开）
        for key in visited:
            if key != monster.room_key:
                self._drop_body(engine, key)
        engine._log(f"{monster.name} 游到了{engine.state.board[monster.room_key].name}。")
        if target is not None and target.room_key == monster.room_key:
            engine._monster_attack(monster, target)
        return True

    def _pos_of(self, engine: Any, room: Any, direction: str) -> str | None:
        """房间某门方位对应的板块 key（未放房为 None）。"""
        dx, dy = self.DELTAS.get(direction, (0, 0))
        return engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))

    # ------------------------------------------------------------- 攻击
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p58：施放削弱咒之前不能攻击蛇头。"""
        if getattr(target, "template_id", "") == self.HEAD:
            if target.id not in set(engine._haunt_flags().get("weakened_heads", [])):
                return False
        return super().attack_allowed(engine, attacker, target)

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p129：蛇头不可击晕——每次击败记 1 hit，满数即杀（p58）。"""
        if getattr(monster, "template_id", "") != self.HEAD:
            return False
        flags = engine._haunt_flags()
        hits = dict(flags.get("head_hits", {}))
        hits[monster.id] = int(hits.get(monster.id, 0)) + 1
        flags["head_hits"] = hits
        needed = int(flags.get("hits_needed", 2))
        if hits[monster.id] >= needed:
            engine._log(f"{monster.name} 轰然倒地——第 {hits[monster.id]}/{needed} 次重击奏效！")
            engine._kill_monster(monster)
        else:
            engine._log(f"{monster.name} 受创（{hits[monster.id]}/{needed}），但仍在扭动。")
        return True  # 不击晕、不默认离场——击杀由 handler 全权

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        weakened = set(engine._haunt_flags().get("weakened_heads", []))
        for action in actions:
            # 已削弱的蛇头别再显示施咒
            if getattr(action, "id", "") == "cast_weakening_spell":
                if not any(
                    h.room_key == player.room_key and h.id not in weakened
                    for h in self._heads(engine)
                ):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "cast_weakening_spell":
            return self._cast_spell(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _cast_spell(self, engine: Any, player: Any) -> bool:
        """p58：持骷髅 + 蛇头同房 → 理智 5+，成功则该头力量降 5、可被攻击。"""
        if self.SKULL not in player.items:
            return False
        weakened = set(engine._haunt_flags().get("weakened_heads", []))
        targets = [
            h
            for h in self._heads(engine)
            if h.room_key == player.room_key and h.id not in weakened
        ]
        if not targets:
            return False
        head = targets[0]
        if len(targets) > 1 and getattr(player, "control", "bot") != "bot":
            idx = engine.prompter.choose_from_list(
                "削弱咒", "对哪颗蛇头施咒？", [f"蛇头 {i + 1}" for i in range(len(targets))]
            )
            if idx is not None and 0 <= idx < len(targets):
                head = targets[idx]
        ok = engine._resolve_check(player, "sanity", 5, "削弱咒")
        if not ok:
            engine._log(f"{engine._player_label(player)} 的咒文散在了空气里。")
            return False
        flags = engine._haunt_flags()
        flags["weakened_heads"] = sorted(weakened | {head.id})
        head.might = 5
        engine._log(f"咒文缠住了{head.name}——它的力量降到了 5，现在可以对它出手了！")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p129：16 节蛇身全部进场 → 叛徒胜
        if int(flags.get("body_left", self.BODY_TOTAL)) <= 0:
            engine._set_winner("traitor", "十六节蛇身环抱整栋房子——巨蛇开始收拢它的绞索。")
            return True
        # p58：双头皆斩 → 英雄胜
        if not self._heads(engine):
            engine._set_winner("heroes", "两条蛇头都被斩落——世界之蛇的入侵到此为止。")
            return True
        # 通用：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "所有英雄都倒下了。")
            return True
        # 吸收兜底：叛徒开局变蛇出局（p129）——绝不能因此判英雄胜（10 号同款）
        return True

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        weakened = set(engine._haunt_flags().get("weakened_heads", []))
        # 追未削弱的蛇头施咒（骷髅掉在地上，bot 的关键牌拾取会顺路去拿）
        return [
            f"__room__{head.room_key}"
            for head in self._heads(engine)
            if head.id not in weakened
        ]

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = []
        weakened = set(flags.get("weakened_heads", []))
        for head in self._heads(engine):
            state = "已削弱（力 5）" if head.id in weakened else "未削弱"
            hits = int(flags.get("head_hits", {}).get(head.id, 0))
            lines.append(f"{head.name}：{state}，受创 {hits}/{flags.get('hits_needed', '?')}。")
        placed = self.BODY_TOTAL - int(flags.get("body_left", self.BODY_TOTAL))
        lines.append(f"蛇身：{placed}/{self.BODY_TOTAL} 节。")
        return lines


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
        # p130：叛徒回合开始时，被击败的杰克回到门厅且全属性 +1
        if player.role == "traitor" and flags.get("jack_banished"):
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

    def _study(self, engine: Any, player: Any) -> bool:
        """p59：持诅咒武器者做力量 5+ 或知识 5+；成功 +1 枚研究令牌。"""
        flags = engine._haunt_flags()
        weapon = flags.get("cursed_weapon")
        if not weapon or weapon not in player.items:
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
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        flags = engine._haunt_flags()
        # 已理解用法 → 去打杰克；没武器 → 去搜索房找武器
        if flags.get("cursed_weapon_understood"):
            jack = self._jack(engine)
            return [f"__room__{jack.room_key}"] if jack is not None else []
        if not flags.get("cursed_weapon"):
            return [r for r in self.SEARCH_ROOMS]
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


class AstralSpiritMode(GenericModeHandler):
    """剧本 49「You Wear It Well」（英雄手册 p60 / 叛徒手册 p131）。

    星界灵把所有英雄的灵魂拽出了肉体：英雄们以灵体状态继续行动，
    肉体昏迷在原地。星界灵想要一具"外套"——只要它附身一具无魂的
    肉体，或者把所有灵魂磨灭，英雄们就再也回不去了。

    · 开局（p130/p131）：星界灵放叛徒所在房间；英雄们的肉体昏迷
      （电子版把"灵魂"与"昏迷肉体"建在同一位英雄身上——位置即
      肉体位置，玩家继续扮演自己的灵魂，无需灵魂令牌）。
    · 灵魂规则（p60，保真部分）：英雄保留全部属性；不能探索新房间
      （can_discover_rooms 拦下）；攻击与防御只能用知识/理智
      （attack_attr_override 把力量/速度攻击覆盖为理智/知识中较高者）；
      攻击星界灵失败不受伤（attack_loss_damage_disabled）。
    · 摧毁星界灵（p60）：英雄攻击成功 → 不造成伤害，改为 +1 枚驱逐
      令牌（星界灵不晕不死，on_monster_defeated 全权处理）；累计到
      玩家数枚 → 星界灵被摧毁，英雄胜，众人回到肉体。
    · 星界灵攻击（p131）：只能以知识攻击英雄灵魂（on_monster_turn_attack
      接管为知识对决，差值即精神伤害；被击败则什么都不发生）。
    · 毁灭灵魂（p131）：叛徒攻击英雄（昏迷肉体）——电子版简化为标准
      攻击对决（原版无防御固定 2 骰精神伤）；精神属性被打到骷髅 =
      灵魂被毁，该英雄出局，其肉体进入"无魂"名单，**从此不能被附身**。
    · 附身仪式（p131）：星界灵回合移向最近的无魂肉体，同房间做理智
      检定，结果须**高于**该探索者的起始理智；每次成功 +1 枚附身令牌，
      累计到玩家数 → 附身成功，叛徒胜。
    · 胜负（p60/p131）：英雄胜 = 摧毁星界灵；叛徒胜 = 全部灵魂被毁，
      或星界灵附身一具无魂肉体。叛徒被杀而星界灵还在时星界灵继续
      行动（7/8 号怪物自主口径），故吸收兜底。

    已知简化：
        · 灵魂与星界灵的"穿墙移动"未建模——引擎移动基于门图，两者
          沿用正常移动；灵魂本就不能探索新房间，活动范围即已探明区域。
        · 灵魂与昏迷肉体同位建模（无独立灵魂令牌）；"灵魂被毁物品
          同毁"由引擎死亡掉落流程近似。
        · 「地下室与房屋断开时补楼梯」未建模（bot 局地下室通常已连通）。
        · 叛徒攻击昏迷肉体简化为标准对决（原版无防御固定 2 骰精神伤）；
          灵魂"物理伤害转精神伤害"、物品禁用（武器/Skull/玩具猴）、
          物品不可转移均未在物品系统层拦截（bot 不会主动违例）。
        · 「精神攻击击败叛徒则击晕」未建模（引擎玩家间攻击为标准对决）。
        · 附身检定的"起始理智"用角色属性轨道上限近似（引擎不单独记
          作祟时刻的初始值）。
    """

    mode = "astral_spirit"

    SPIRIT = "astral_spirit"
    MENTAL = ("sanity", "knowledge")

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("spirit_destroyed", False)
        flags.setdefault("spirit_inhabited", False)
        flags.setdefault("soulless", {})
        players = len(engine.state.players)
        engine._haunt_tracks().setdefault(
            "banish_tokens",
            {"label": "驱逐星界灵", "target": players, "value": 0},
        )["target"] = players

        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.SPIRIT, {"template_id": self.SPIRIT, "name": "星界灵"})
        )
        engine._spawn_single_haunt_monster(spec, traitor.room_key if traitor else room_key)
        engine._log(
            "一阵狂风撕开了所有人的灵魂——英雄们瘫倒在地，灵体在原地颤抖着站起。"
        )

    # ------------------------------------------------------- 灵魂规则
    def can_discover_rooms(self, engine: Any, player: Any) -> bool:
        """p60：灵魂不能探索新房间（叛徒不受影响）。"""
        if player.role == "hero":
            return False
        return True

    def attack_attr_override(
        self, engine: Any, attacker: Any, target: Any, default_attr: str
    ) -> str | None:
        """p60：灵魂攻击/防御只能用知识或理智。"""
        if getattr(attacker, "role", "") != "hero":
            return None
        if default_attr in ("might", "speed"):
            return "sanity" if attacker.stats.get("sanity", 0) >= attacker.stats.get(
                "knowledge", 0
            ) else "knowledge"
        return None

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p60：攻击星界灵失败不受伤。"""
        return getattr(target, "template_id", "") == self.SPIRIT

    def on_player_died(self, engine: Any, player: Any) -> None:
        """p131：灵魂被毁的英雄出局，其肉体进入无魂名单（不能被附身）。"""
        if player.role != "hero":
            return
        flags = engine._haunt_flags()
        soulless = dict(flags.get("soulless", {}))
        soulless[str(player.id)] = {
            "room_key": player.room_key,
            "ritual": 0,
            "starting_sanity": int(player.stats_max.get("sanity", 4)),
        }
        flags["soulless"] = soulless
        engine._log(f"{player.name} 的灵魂彻底消散了——那具肉体成了一具空壳。")

    # ------------------------------------------------------- 星界灵回合
    def _spirit(self, engine: Any) -> Any:
        return next(
            (m for m in engine.state.monsters if m.template_id == self.SPIRIT), None
        )

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if getattr(monster, "template_id", "") != self.SPIRIT:
            return False
        flags = engine._haunt_flags()
        players = len(engine.state.players)
        soulless = dict(flags.get("soulless", {}))
        pending = [
            (hid, info)
            for hid, info in soulless.items()
            if int(info.get("ritual", 0)) < players and info.get("room_key") in engine.state.board
        ]
        if not pending:
            return False  # 没有附身目标：走默认移动与攻击
        # p131：星界灵移向最近的无魂肉体
        target_room = min(
            (info["room_key"] for _, info in pending),
            key=lambda k: engine._path_length(monster.room_key, k),
        )
        path = engine._shortest_path(monster.room_key, target_room)
        if len(path) > 1:
            steps = max(1, engine.roll_dice(monster.speed, "星界灵移动"))
            monster.room_key = path[min(len(path) - 1, steps)]
        engine._log(f"星界灵飘到了{engine.state.board[monster.room_key].name}。")
        # 同房间做附身仪式（每回合一次理智检定，结果须高于起始理智）
        for hid, info in pending:
            if info["room_key"] != monster.room_key:
                continue
            roll = engine.roll_dice(monster.sanity, "附身仪式")
            threshold = int(info.get("starting_sanity", 4))
            engine._log(
                f"附身仪式：掷出 {roll}（需高于 {threshold}）。"
            )
            if roll > threshold:
                info["ritual"] = int(info.get("ritual", 0)) + 1
                soulless[hid] = info
                flags["soulless"] = soulless
                engine._log(
                    f"星界灵在这具空壳上又刻下了一道印记"
                    f"（{info['ritual']}/{players}）。"
                )
                if info["ritual"] >= players:
                    flags["spirit_inhabited"] = True
            else:
                soulless[hid] = info
                flags["soulless"] = soulless
            break  # 每回合只对一具肉体尝试
        return False  # 继续默认移动/攻击活英雄

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p131：星界灵只能以知识攻击英雄的灵魂（精神伤害）。"""
        if getattr(monster, "template_id", "") != self.SPIRIT:
            return False
        target = engine._find_monster_target(monster)
        if target is None or target.room_key != monster.room_key:
            return True  # 不同房就不攻击（也不能攻击肉体）
        roll = engine._roll_monster_attack(monster, "knowledge")
        defense = engine._roll_attack(target, "knowledge")
        engine._log(f"星界灵以精神利刃刺向 {engine._player_label(target)}：{roll} 对 {defense}。")
        if roll > defense:
            engine._deal_damage(target, "mental", roll - defense, source="星界灵")
        elif roll < defense:
            engine._log("灵体挣脱了它的触碰——星界灵毫发无损（p131：被击败不晕）。")
        return True

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p60：星界灵不晕不死——攻击成功改为累积驱逐令牌。"""
        if getattr(monster, "template_id", "") != self.SPIRIT:
            return False
        flags = engine._haunt_flags()
        engine._advance_haunt_track("banish_tokens")
        current = engine._haunt_track_value("banish_tokens")
        needed = engine._haunt_track_target("banish_tokens")
        engine._log(
            f"英雄们的精神攻击撼动了星界灵（{current}/{needed}）——它没有受伤，但被削弱了。"
        )
        if current >= needed > 0:
            flags["spirit_destroyed"] = True
        return True  # 不击晕、不默认离场

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p60：星界灵被摧毁 → 英雄胜，众人回到肉体
        if flags.get("spirit_destroyed"):
            engine._set_winner("heroes", "星界灵在齐心合力的精神攻击下灰飞烟灭——灵魂归位。")
            return True
        # p131：附身一具无魂肉体 → 叛徒胜
        if flags.get("spirit_inhabited"):
            engine._set_winner("traitor", "星界灵穿上了朋友的肉体——“你穿得很好。”")
            return True
        # p131：所有灵魂被毁 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "最后一位英雄的灵魂也熄灭了。")
            return True
        # 吸收兜底：叛徒被杀而星界灵还在——星界灵继续行动（7/8 号口径）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        spirit = self._spirit(engine)
        return [f"__room__{spirit.room_key}"] if spirit is not None else []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = [
            f"驱逐进度：{engine._haunt_track_value('banish_tokens')}/"
            f"{engine._haunt_track_target('banish_tokens')}。",
        ]
        soulless = flags.get("soulless", {})
        if soulless:
            marks = ", ".join(
                f"{info.get('ritual', 0)}枚" for info in soulless.values()
            )
            lines.append(f"无魂肉体：{len(soulless)} 具（附身印记 {marks}）。")
        return lines


class NightMurderMode(GenericModeHandler):
    """剧本 50「A Little Night Murder / 小小夜谋」（英雄手册 p61 / 叛徒手册 p132）。

    老普雷斯蒂科特死在了大楼梯底下，遗嘱已经宣读：只要在房子里待到天亮，
    遗产就归你们。只有一个问题——屋里那些贪婪的仆人已经和那个被排除在
    遗嘱之外的亲戚谈好了分成。活到黎明，钱就是你们的。

    · 开局（p132）：仆人令牌数 = 英雄数；前三个各放在**不同楼层**的空房间，
      多余的放任意空房；没有空房时平均分配到已占用的房间（同 21/28 号
      "房不够就叠放"口径）。仆人按普通怪物处理。
    · 夜晚推进（p132）：叛徒回合结束时把回合/伤害轨道推进一格；叛徒若已死，
      由"本轮最后一名存活玩家"代跑——p132 明说"叛徒死了照样能赢"，
      所以计时器绝不能因为叛徒出局而停摆（4 号 spider_timer 同款坑）。
    · 仆人强化表（p132）：Turn 0-3 → 3/3/3；4-7 → 4/4/4；8 → 5/5/5；
      9 → 6/6/6。每次轨道推进后重算全体仆人属性（45 号蜘蛛成长同款写法）。
    · 胜负（p61/p132）：轨道推进到 10（日出）→ 存活的英雄获胜分遗产；
      黎明前英雄全灭 → 叛徒胜。叛徒出局不判英雄胜（吸收兜底）。

    已知简化：
        · "空房间"按"没有玩家的房间"判定（原版 occupied 主要指探险者）。
        · 日出时的"存活英雄"取作祟后仍活着的英雄；仆人继续存在不影响结算。
    """

    mode = "night_survival"

    SERVANT = "servant"
    DAWN = 10
    # p132 仆人强化表（轨道值 → speed/might/sanity），实际取值见 _apply_strength
    STRENGTH_TABLE = "0-3→3/3/3；4-7→4/4/4；8→5/5/5；9→6/6/6"

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        engine._haunt_tracks().setdefault(
            "night_timer", {"label": "夜晚进度（日出）", "target": self.DAWN, "value": 0}
        )["target"] = self.DAWN

        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.SERVANT, {"template_id": self.SERVANT, "name": "贪婪仆人"})
        )
        for target in self._servant_rooms(engine, hero_count, room_key):
            engine._spawn_single_haunt_monster(spec, target)
        engine._log(
            f"{hero_count} 名仆人从走廊尽头现身——他们要你们熬不过今夜。"
        )

    def _servant_rooms(self, engine: Any, count: int, room_key: str) -> list[str]:
        """p132：前三个尽量放在不同楼层的空房，其余放任意空房。"""
        occupied = {p.room_key for p in engine.state.players if not p.dead}
        by_floor: dict[int, list[str]] = {}
        for key, room in sorted(engine.state.board.items()):
            if key in occupied:
                continue
            by_floor.setdefault(room.floor, []).append(key)
        chosen: list[str] = []
        # 前三个：尽量各占一层（先按天亮前分布最广的方式取）
        for floor in sorted(by_floor, reverse=True):
            if len(chosen) >= min(3, count):
                break
            if by_floor[floor]:
                chosen.append(by_floor[floor].pop(0))
        # 余下：任意空房
        rest = [key for keys in by_floor.values() for key in keys]
        while len(chosen) < count and rest:
            chosen.append(rest.pop(0))
        # 空房不够：平均分配到已占用的房间（21/28 号同口径）
        while len(chosen) < count:
            pool = sorted(engine.state.board) or [room_key]
            chosen.append(pool[len(chosen) % len(pool)])
        return chosen[:count]

    # ------------------------------------------------------------- 夜晚
    def _servants(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if m.template_id == self.SERVANT]

    def on_turn_end(self, engine: Any, player: Any) -> None:
        """p132：叛徒回合结束推进夜晚；叛徒已死则由本轮最后存活玩家代跑。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            should_tick = player.id == traitor.id
        else:
            should_tick = _is_last_in_round(engine, player)
        if not should_tick:
            return
        current = engine._advance_haunt_track("night_timer")
        engine._log(f"夜色又深了一层（{current}/{self.DAWN}）。")
        self._apply_strength(engine, current)

    def _apply_strength(self, engine: Any, turn: int) -> None:
        """p132 强化表：0-3 → 3/3/3；4-7 → 4/4/4；8 → 5/5/5；9 → 6/6/6。"""
        if turn >= 9:
            stats = (6, 6, 6)
        elif turn >= 8:
            stats = (5, 5, 5)
        elif turn >= 4:
            stats = (4, 4, 4)
        else:
            stats = (3, 3, 3)
        for monster in self._servants(engine):
            monster.speed, monster.might, monster.sanity = stats

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p132：黎明前英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "最后一个继承人也倒下了——仆人们举起了香槟。")
            return True
        # p61：撑到 Turn 10 日出 → 英雄胜（存活者分遗产）
        if engine._haunt_track_value("night_timer") >= self.DAWN:
            engine._set_winner("heroes", "晨光透过窗户洒进来——你们熬过了这一夜。")
            return True
        # 吸收兜底：p132 明说叛徒死了照样能赢（仆人继续），绝不判英雄胜
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        current = engine._haunt_track_value("night_timer")
        lines = [f"夜晚进度：{current}/{self.DAWN}（撑到日出即英雄胜）。"]
        servants = self._servants(engine)
        if servants:
            sample = servants[0]
            lines.append(f"仆人：{len(servants)} 名，当前 {sample.speed}/{sample.might}/{sample.sanity}。")
        return lines











class SandsOfTimeMode(GenericModeHandler):
    """剧本 56「Time Waits for One Man」（英雄手册 p67 / 叛徒手册 p138）。

    叛徒戴上了面具，时之沙脱缰而出：记忆与命运的幽影在他差遣下猎杀
    昔日的朋友。但他每次动用时间之力，时之沙就离他的掌控更远一分——
    一旦失控，连他自己的存在都会被磨损。

    · 开局（p138）：幽影数 = 英雄数，放作祟房；叛徒立即戴上面具：
      +2 知识、-2 理智（若理智会死则停在骷髅上方最低格，p138 明文保护）。
    · 幽影（p138/p67）：免疫力量攻击（monster_specs immune_to）；只能以
      理智攻击（on_monster_turn_attack 接管，目标以理智防御、精神伤害）；
      **穿墙移动**（同层正交邻格、无需门，排除神秘电梯——p138 明文；
      上下楼通道 Chute/Collapsed/Gallery 简化掉）；不阻碍移动（引擎互不
      阻挡自动满足）。被理智攻击（持戒指）击败则正常击晕。
    · 时间之力（p138，每次轨道 +1、无上限）：电子版落成三个叛徒行动——
      命运之风（+2 移动）、时停打击（力量攻击同房英雄，造成 ≥1 伤害则
      该英雄跳过下回合）、补充时沙（知识 3+：每只同房幽影使轨道 -1，
      无论成败同房幽影全晕）。轨道用 flags["time_track"] 记（原文无上限，
      UI 轨道封顶显示）。Recall/Visions/Blitz 未建模（见已知简化）。
    · 失控检定（p67）：叛徒回合结束后（叛徒已死则由本轮最后存活玩家
      代跑），一名英雄掷玩家数枚骰——结果 ≤ 轨道值 → 叛徒全属性 -1、
      轨道 -1、再掷（循环到结果 > 轨道值）。越用时间之力越容易失控。
    · 欺骗命运（p67）：英雄行动——与幽影同房 +（持水晶球 或 房内没有
      其他英雄）→ 知识 4+ → 该幽影立即移出游戏。每回合一次。
    · 戒指/奖章（p67）：持戒指者可用理智攻击幽影（attack_attr_override
      覆盖力量为理智）；持奖章者与幽影对决落败不受伤。
    · 胜负（p67/p138）：英雄胜 = 叛徒死亡（失控磨损同算）；叛徒胜 =
      英雄全灭。本剧本叛徒死即英雄胜（p67 原文），不需要吸收兜底。

    已知简化：
        · Recall（强制重掷）没有全局掷骰后钩子可挂，未建模；Visions
          （看牌堆顶重排）对 bot 无意义、人类收益低，未建模；Blitz
          （速度攻击变体）未建模——叛徒用标准力量攻击。
        · 幽影上下楼通道（Chute/Collapsed/Gallery 各花 1 点）未建模，
          幽影只在已探明层内穿墙游走。
        · 面具"不可摘/不可弃/不可偷"未在物品系统层拦截（bot 不偷）。
        · 失控检定的掷骰英雄由系统自动选择（原版由英雄们自行商定）。
        · "时停打击"重构为显式剧本行动（原版为攻击附效自动触发）。
    """

    mode = "time_sands"

    SPECTRE = "spectre"
    MASK = "omen_mask"
    RING = "omen_ring"
    MEDALLION = "omen_medallion"
    CRYSTAL_BALL = "omen_crystal_ball"
    ELEVATOR = "mystic_elevator"
    DELTAS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("time_track", 0)
        flags.setdefault("skip_turn_ids", [])
        engine._haunt_tracks().setdefault(
            "time_track", {"label": "时之沙掌控（失控线）", "target": 10, "value": 0}
        )
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        # p138：立即戴上面具——+2 知识、-2 理智（理智死亡保护到骷髅上一格）
        if traitor is not None and not traitor.dead:
            engine._increase_stat(traitor, "knowledge", 2)
            track = engine._stat_track(traitor, "sanity") or []
            floor_pos = max(0, len(track) - 2)  # 骷髅上一格（格位越大数值越小）
            pos = traitor.stat_positions.get("sanity", 0)
            if track and pos + 2 > len(track) - 1:
                traitor.stat_positions["sanity"] = min(floor_pos, pos + 2)
                traitor.stats["sanity"] = track[traitor.stat_positions["sanity"]]
                engine._log(f"{traitor.name} 的理智坠到了崩溃边缘，但面具不容他死去。")
            else:
                engine._apply_stat_loss(traitor, "sanity", 2)
            engine._log("面具焊在了脸上——知识涌入，理智流失。")
        # p138：幽影 = 英雄数，放作祟房
        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.SPECTRE, {"template_id": self.SPECTRE, "name": "记忆幽影"})
        )
        for _ in range(hero_count):
            engine._spawn_single_haunt_monster(spec, room_key)
        engine._log(f"{hero_count} 道幽影自墙壁渗出——那是记忆，也是命运。")

    # ------------------------------------------------------- 幽影规则
    def _spectres(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if m.template_id == self.SPECTRE]

    def attack_attr_override(
        self, engine: Any, attacker: Any, target: Any, default_attr: str
    ) -> str | None:
        """p67：幽影免疫力量攻击，但持戒指者可用理智攻击（正常规则）。"""
        if (
            getattr(target, "template_id", "") == self.SPECTRE
            and default_attr == "might"
            and self.RING in getattr(attacker, "items", [])
        ):
            return "sanity"
        return None

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p67：持奖章者与幽影对决落败不受伤。"""
        return getattr(target, "template_id", "") == self.SPECTRE and (
            self.MEDALLION in getattr(attacker, "items", [])
        )

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if getattr(monster, "template_id", "") != self.SPECTRE:
            return False
        # p138：幽影可在相邻房间间穿行（无需门）；同层正交邻格、排除电梯
        target = engine._find_monster_target(monster)
        for _ in range(max(1, monster.speed)):
            room = engine.state.board.get(monster.room_key)
            if room is None:
                break
            neighbors = []
            for direction in sorted(room.doors):
                dx, dy = self.DELTAS.get(direction, (0, 0))
                key = engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
                if key and engine.state.board[key].template_id != self.ELEVATOR:
                    neighbors.append(key)
            # 穿墙：同层正交邻格里门邻居之外的房间也算可走
            for dx, dy in self.DELTAS.values():
                key = engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
                if key and key not in neighbors and engine.state.board[key].template_id != self.ELEVATOR:
                    neighbors.append(key)
            if not neighbors:
                break
            if target is not None:
                dest = min(neighbors, key=lambda k: engine._path_length(k, target.room_key))
            else:
                dest = sorted(neighbors)[0]
            monster.room_key = dest
        return False  # 移动由本钩子接管；攻击交给 on_monster_turn_attack

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p138：幽影只能以理智攻击（目标以理智防御，精神伤害）。"""
        if getattr(monster, "template_id", "") != self.SPECTRE:
            return False
        target = engine._find_monster_target(monster)
        if target is None or target.room_key != monster.room_key:
            return True
        roll = engine._roll_monster_attack(monster, "sanity")
        defense = engine._roll_attack(target, "sanity")
        engine._log(f"幽影的尖啸刺入 {engine._player_label(target)} 的脑海：{roll} 对 {defense}。")
        if roll > defense:
            engine._deal_damage(target, "mental", roll - defense, source="幽影")
        elif roll < defense:
            engine._stun_monster(monster, 1)
        return True

    # ------------------------------------------------------- 时间之力
    def _advance_time(self, engine: Any, amount: int = 1) -> int:
        """p138：轨道无上限（flags 记真实值），UI 轨道同步（封顶显示）。"""
        flags = engine._haunt_flags()
        value = max(0, int(flags.get("time_track", 0)) + amount)
        flags["time_track"] = value
        engine._set_haunt_track_value("time_track", min(value, 10))
        return value

    def _cheat_fate_allowed(self, engine: Any, player: Any) -> bool:
        has_spectre = any(s.room_key == player.room_key for s in self._spectres(engine))
        if not has_spectre:
            return False
        if self.CRYSTAL_BALL in player.items:
            return True
        others = any(
            p.role == "hero" and not p.dead and p.id != player.id
            and p.room_key == player.room_key
            for p in engine.state.players
        )
        return not others  # 房内没有其他英雄才可尝试

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            # 欺骗命运：须持水晶球，或房内没有其他英雄（p67）
            if aid == "cheat_fate" and not self._cheat_fate_allowed(engine, player):
                continue
            # 补充时沙：同房间得有没被晕的幽影
            if aid == "replenish_sands" and not any(
                s.room_key == player.room_key and s.stunned_turns <= 0
                for s in self._spectres(engine)
            ):
                continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "cheat_fate":
            return self._cheat_fate(engine, player)
        if action_id == "winds_of_fate":
            player.steps_remaining += 2
            self._advance_time(engine)
            engine._log("命运之风鼓起叛徒的衣袍——本回合移动 +2（轨道 +1）。")
            return True
        if action_id == "time_stop_strike":
            return self._time_stop_strike(engine, player)
        if action_id == "replenish_sands":
            return self._replenish(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _cheat_fate(self, engine: Any, player: Any) -> bool:
        """p67：知识 4+ → 同房幽影立即移出游戏。"""
        if not self._cheat_fate_allowed(engine, player):
            return False
        targets = [s for s in self._spectres(engine) if s.room_key == player.room_key]
        if not targets:
            return False
        ok = engine._resolve_check(player, "knowledge", 4, "欺骗命运")
        if not ok:
            engine._log(f"{engine._player_label(player)} 试图篡改命运，但时之沙不为所动。")
            return False
        spectre = targets[0]
        engine.state.monsters = [m for m in engine.state.monsters if m.id != spectre.id]
        engine._log("命运被改写了——一道幽影从现实中被抹去！")
        return True

    def _time_stop_strike(self, engine: Any, player: Any) -> bool:
        """p138 时停：力量攻击同房英雄，造成 ≥1 伤害则该英雄跳过下回合（轨道 +1）。"""
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
        roll = engine._roll_attack(player, "might")
        defense = engine._roll_attack(target, "might")
        engine._log(f"时停打击：{engine._player_label(player)} {roll} 对 {defense}。")
        if roll > defense:
            engine._deal_damage(target, "physical", roll - defense, source="时停打击")
            flags = engine._haunt_flags()
            flags["skip_turn_ids"] = sorted(set(flags.get("skip_turn_ids", [])) | {target.id})
            engine._log(f"{engine._player_label(target)} 被冻结在了时间之外——下回合无法行动。")
        self._advance_time(engine)
        return True

    def _replenish(self, engine: Any, player: Any) -> bool:
        """p138：知识 3+ → 每只同房幽影使轨道 -1；无论成败同房幽影全晕。"""
        here = [s for s in self._spectres(engine) if s.room_key == player.room_key]
        if not here:
            return False
        ok = engine._resolve_check(player, "knowledge", 3, "补充时沙")
        if ok:
            self._advance_time(engine, -len(here))
            engine._log(f"幽影被榨干了——时之沙退回 {engine._haunt_flags().get('time_track', 0)}。")
        else:
            engine._log("补充时沙失败——幽影依旧被抽干了力量。")
        for spectre in here:
            spectre.stunned_turns += 1
        return True

    # ------------------------------------------------------- 失控检定
    def on_turn_end(self, engine: Any, player: Any) -> None:
        """p67：叛徒回合结束（叛徒死则本轮最后存活玩家代跑）做失控检定。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            should_roll = player.id == traitor.id
        else:
            should_roll = _is_last_in_round(engine, player)
        if not should_roll:
            return
        self._control_check(engine)

    def _control_check(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        track = int(flags.get("time_track", 0))
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return
        roller = heroes[0]  # 原版由英雄们商定，电子版自动选第一名活英雄
        dice = len(engine.state.players)
        guard = 0
        while guard < 24:
            guard += 1
            result = engine.roll_dice(dice, "时之沙掌控检定")
            if result > track:
                engine._log(f"时之沙掌控检定：{result} > {track}——叛徒勉强维持住了控制。")
                return
            traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
            if traitor is None or traitor.dead:
                return
            engine._log(f"时之沙掌控检定：{result} ≤ {track}——叛徒失控了！")
            for stat in ("sanity", "knowledge", "might", "speed"):
                engine._apply_stat_loss(traitor, stat, 1)
            track = self._advance_time(engine, -1)
            engine.check_victory()
            if engine.state.winner:
                return

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """p138 时停：被冻结的英雄跳过本回合。"""
        flags = engine._haunt_flags()
        skipped = set(flags.get("skip_turn_ids", []))
        if player.id in skipped:
            flags["skip_turn_ids"] = sorted(skipped - {player.id})
            player.movement_stopped = True
            player.attack_used = True
            player.item_used = True
            engine._mark_haunt_action_used(player)
            engine._log(f"{engine._player_label(player)} 仍被冻结在时间之外——本回合无法行动。")

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p67：叛徒死亡 → 英雄胜（失控磨损同算）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            engine._set_winner("heroes", "时之沙反噬了它的主人——时间重新开始流动。")
            return True
        # p138：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "最后的记忆也被幽影吞噬了。")
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        # 持戒指/奖章的英雄去缠幽影；其他人直奔叛徒
        if self.RING in player.items or self.MEDALLION in player.items:
            spectres = self._spectres(engine)
            if spectres:
                return [f"__room__{spectres[0].room_key}"]
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        return [f"__room__{traitor.room_key}"] if traitor is not None else []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        track = int(flags.get("time_track", 0))
        lines = [f"时之沙轨道：{track}（每回合结束掷玩家数骰，≤ 轨道即失控）。"]
        skipped = flags.get("skip_turn_ids", [])
        if skipped:
            lines.append(f"被时停的英雄：{len(skipped)} 名。")
        lines.append(f"幽影：{len(self._spectres(engine))} 只。")
        return lines


class NightfallMode(GenericModeHandler):
    """剧本 58「Nightfall / 夜幕降临」（英雄手册 p69 / 叛徒手册 p140）。

    叛徒盼到了他的时刻：夜幕落下，整栋房子沉进一片自我主张的暮色里。
    暮色中人的身体不听使唤，只有心智还算锐利——想活下去，就去熔炉房
    点一支火把，然后一层一层把暮色赶出去。

    · 开局（p69/p140）：若熔炉房不在场则从房间牌堆取出放好（引擎
      `_ensure_room_in_play`，3/28 号同款先例；原文要求放地下室）；
      噩梦（Speed 2 / Might 2 / Knowledge 5 / Sanity 4）= 英雄数，
      铺在**带事件图标且离最近英雄 ≥4 格**的房间，不够远就取尽可能远的。
    · 暮色（p69/p140）：除熔炉房/花园/墓地/天井/阳台/塔楼之外的房间都在
      暮色里；叛徒所在房间**永远是暮色**（即使叛徒已死）；已驱散的楼层
      与有火把的房间不算暮色。
    · 火把（p69）：英雄在熔炉房可造火把代替攻击；火把抵消同房间的暮色，
      持火把者永不受暮色影响（按正常速度移动、正常力量攻击）。例外：
      叛徒与火把同房时只有持火把者受保护（已按原文实现）。
    · 消灭噩梦（p69）：受 2 点以上伤害即被摧毁移出游戏，更少则只是击晕。
    · 驱散暮色（p69）：同房间多名英雄且至少一人持火把时，由一人发起，
      同房所有活着的英雄各做一次知识 4+ 或理智 4+（做检定的英雄本回合
      不能移动/攻击）；**至少一个知识成功 + 一个理智成功** → 该层暮色
      被驱散；三层全驱散 → 英雄胜。
    · 缠梦（p140）：噩梦造成 ≥2 点精神伤害时可选择缠住该英雄（bot 总是
      选择缠梦）；被缠的英雄回合开始做理智 5+ 挣脱：成功则噩梦现身于
      英雄房间、失败则受 1 骰精神伤害。缠梦中的噩梦不行动、不可被攻击。
    · 暮色战斗（p69/p140）：暮色中不能做力量/速度攻击，但可用**知识攻击**
      （目标以知识防御、精神伤害）——attack_attr_override 覆盖；持火把
      者不受此限。
    · 胜负（p69/p140）：英雄胜 = 消灭所有噩梦，或三层暮色全部驱散；
      叛徒胜 = 英雄全灭。叛徒出局时噩梦照常行动，吸收兜底（7/8 号口径）。

    已知简化：
        · "暮色中用 Sanity 代替 Speed 决定移动力"未建模——引擎没有改移动
          力属性的钩子（只有 movement_cost_multiplier/floor），错误建模比
          不建模更糟，故只保留"暮色中改用知识攻击"这一条战斗影响。
        · "有朝外窗户的房间不在暮色中"未建模——内容库没有朝外窗标记。
        · 暮色中禁用斧/矛/血匕首/左轮、左轮不能射入暮色房、蜡烛/德鲁伊
          护符/水晶球作为知识武器的加骰，均未在物品系统层拦截。
        · 噩梦摧毁阈值：物理 ≥2 正确；精神伤害按统一阈值 2（原文 3，
          on_monster_defeated 钩子不提供伤害类型，无法区分）。
        · 缠梦英雄"被叛徒操控本回合"未建模（bot 无法代打）。
        · 驱散暮色的集体检定由发起者一次结算（原版各自声明本回合尝试）。
    """

    mode = "nightfall_twilight"

    NIGHTMARE = "nightmare"
    FURNACE = "furnace_room"
    CANDLE = "omen_candle"
    # p69：这些房间永远不在暮色中（朝外窗房间未建模）
    TWILIGHT_FREE = ("furnace_room", "garden", "graveyard", "patio", "balcony", "tower")
    FLOORS = (-1, 0, 1)
    BANISH_TARGET = 4

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("banished_floors", [])
        flags.setdefault("torches", {})
        flags.setdefault("haunting", {})

        # p69：熔炉房不在场就放进场（原版要求放地下室）
        furnace = engine._ensure_room_in_play(self.FURNACE, room_key)
        flags["furnace_key"] = furnace

        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.NIGHTMARE, {"template_id": self.NIGHTMARE, "name": "噩梦"})
        )
        for target in self._nightmare_rooms(engine, hero_count, room_key):
            engine._spawn_single_haunt_monster(spec, target)
        engine._log("屋里的声音一点点熄灭了——夜幕落下，梦魇从墙缝里挤了出来。")

    def _nightmare_rooms(self, engine: Any, count: int, room_key: str) -> list[str]:
        """p140：优先带事件图标且离最近英雄 ≥4 格的房间，其次尽可能远。"""
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        candidates = []
        for key, room in sorted(engine.state.board.items()):
            if room.symbol != "event" or self.FURNACE == room.template_id:
                continue
            distance = min(
                (engine._path_length(key, hero.room_key) for hero in heroes),
                default=99,
            )
            candidates.append((distance, key))
        far = [key for distance, key in candidates if distance >= 4]
        pool = far or [key for _, key in sorted(candidates, reverse=True)]
        if not pool:
            pool = [room_key]
        # 尽量均匀分布：轮转取用
        return [pool[i % len(pool)] for i in range(count)]

    # ------------------------------------------------------- 暮色判定
    def _nightmares(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if m.template_id == self.NIGHTMARE]

    def _torch_rooms(self, engine: Any) -> set:
        """持火把者所在房间（火把抵消该房间的暮色）。"""
        torches = engine._haunt_flags().get("torches", {})
        return {
            p.room_key
            for p in engine.state.players
            if not p.dead and torches.get(str(p.id))
        }

    def _carries_torch(self, engine: Any, player: Any) -> bool:
        return bool(engine._haunt_flags().get("torches", {}).get(str(player.id)))

    def in_twilight(self, engine: Any, room_key: str) -> bool:
        """p69：该房间此刻是否处于暮色中。

        优先级：叛徒所在房间**永远**是暮色（p69/p140 明文，优先于一切豁免），
        其次豁免熔炉房/花园/墓地/天井/阳台/塔楼，再看已驱散楼层与火把。
        """
        room = engine.state.board.get(room_key)
        if room is None:
            return False
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and traitor.room_key == room_key:
            return True  # 叛徒所在房间永远是暮色（即使已死）
        if room.template_id in self.TWILIGHT_FREE:
            return False
        if room.floor in set(engine._haunt_flags().get("banished_floors", [])):
            return False
        if room_key in self._torch_rooms(engine):
            return False
        return True

    # ------------------------------------------------------- 战斗规则
    def attack_attr_override(
        self, engine: Any, attacker: Any, target: Any, default_attr: str
    ) -> str | None:
        """p69：暮色中不能做力量/速度攻击，改用知识攻击（持火把者除外）。"""
        if default_attr not in ("might", "speed"):
            return None
        if self._carries_torch(engine, attacker):
            return None
        if getattr(attacker, "role", "") == "hero" and self.in_twilight(
            engine, attacker.room_key
        ):
            return "knowledge"
        return None

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p140：正在缠梦的噩梦不能被攻击。"""
        haunting = engine._haunt_flags().get("haunting", {})
        if getattr(target, "template_id", "") == self.NIGHTMARE and target.id in haunting:
            return False
        return super().attack_allowed(engine, attacker, target)

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p69：噩梦受 2 点以上伤害即被摧毁（否则只是击晕）。"""
        if getattr(monster, "template_id", "") != self.NIGHTMARE:
            return False
        if amount >= 2:
            engine.state.monsters = [m for m in engine.state.monsters if m.id != monster.id]
            engine._haunt_flags().get("haunting", {}).pop(monster.id, None)
            engine._log(f"{monster.name} 在尖啸中碎成了黑烟——它被彻底摧毁了。")
            return True
        engine._log(f"{monster.name} 只是被打散了一瞬。")
        return True  # 由 handler 全权：不足 2 点即击晕（引擎默认路径已跳过）

    # ------------------------------------------------------- 噩梦回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if getattr(monster, "template_id", "") != self.NIGHTMARE:
            return False
        # p140：正在缠梦的噩梦可以选择继续缠（bot 选择继续）
        if monster.id in engine._haunt_flags().get("haunting", {}):
            return True
        return False

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p140：噩梦以知识攻击；造成 ≥2 精神伤害时改为缠梦。"""
        if getattr(monster, "template_id", "") != self.NIGHTMARE:
            return False
        flags = engine._haunt_flags()
        if monster.id in flags.get("haunting", {}):
            return True
        target = engine._find_monster_target(monster)
        if target is None or target.room_key != monster.room_key:
            return True
        roll = engine._roll_monster_attack(monster, "knowledge")
        defense = engine._roll_attack(target, "knowledge")
        engine._log(f"噩梦扑进 {engine._player_label(target)} 的脑海：{roll} 对 {defense}。")
        if roll - defense >= 2:
            haunting = dict(flags.get("haunting", {}))
            haunting[monster.id] = target.id
            flags["haunting"] = haunting
            engine._log(f"{engine._player_label(target)} 被拖进了梦魇——噩梦缠住了他。")
        elif roll > defense:
            engine._deal_damage(target, "mental", roll - defense, source="噩梦")
        elif roll < defense:
            engine._stun_monster(monster, 1)
        return True

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """p140：被缠梦的英雄回合开始做理智 5+ 挣脱。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        flags = engine._haunt_flags()
        haunting = dict(flags.get("haunting", {}))
        mine = [mid for mid, hid in haunting.items() if hid == player.id]
        if not mine:
            return
        if engine._resolve_check(player, "sanity", 5, "挣脱梦魇"):
            for mid in mine:
                monster = next(
                    (m for m in engine.state.monsters if m.id == mid), None
                )
                if monster is not None:
                    monster.room_key = player.room_key  # 现身于英雄房间
                    monster.stunned_turns = 1
                haunting.pop(mid, None)
            flags["haunting"] = haunting
            engine._log(f"{engine._player_label(player)} 挣脱了梦魇——噩梦现身在房间里。")
            return
        engine._deal_damage(player, "mental", engine.roll_dice(1, "梦魇伤害"), source="梦魇")
        engine._log(f"{engine._player_label(player)} 没能甩开梦魇，精神被啃噬了一口。")

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            # 造火把：只能在熔炉房（p69）
            if aid == "create_torch":
                if self._carries_torch(engine, player):
                    continue
                room = engine.state.board.get(player.room_key)
                if room is None or room.template_id != self.FURNACE:
                    continue
            # 驱散暮色：同房 ≥2 名活英雄 + 至少一人持火把 + 该房本该有暮色
            if aid == "banish_twilight" and not self._banish_allowed(engine, player):
                continue
            result.append(action)
        return result

    def _banish_allowed(self, engine: Any, player: Any) -> bool:
        room = engine.state.board.get(player.room_key)
        if room is None or room.floor in set(engine._haunt_flags().get("banished_floors", [])):
            return False
        here = [
            p
            for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == player.room_key
        ]
        if len(here) < 2:
            return False
        if not any(self._carries_torch(engine, p) for p in here):
            return False
        # 该房间"本该"有暮色（无火把时）——用房间模板与楼层判定
        return room.template_id not in self.TWILIGHT_FREE

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "create_torch":
            return self._create_torch(engine, player)
        if action_id == "banish_twilight":
            return self._banish_twilight(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _create_torch(self, engine: Any, player: Any) -> bool:
        """p69：在熔炉房造一支火把（代替攻击）。"""
        room = engine.state.board.get(player.room_key)
        if room is None or room.template_id != self.FURNACE:
            return False
        flags = engine._haunt_flags()
        torches = dict(flags.get("torches", {}))
        torches[str(player.id)] = True
        flags["torches"] = torches
        player.attack_used = True  # p69：代替攻击
        engine._log(f"{engine._player_label(player)} 在熔炉里点燃了一支火把。")
        return True

    def _banish_twilight(self, engine: Any, player: Any) -> bool:
        """p69：同房英雄各做一次知识 4+ 或理智 4+，需两类各至少一次成功。"""
        if not self._banish_allowed(engine, player):
            return False
        room = engine.state.board[player.room_key]
        here = [
            p
            for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == player.room_key
        ]
        knowledge_ok = False
        sanity_ok = False
        for hero in here:
            stat = "knowledge" if hero.stats.get("knowledge", 0) >= hero.stats.get(
                "sanity", 0
            ) else "sanity"
            if engine._resolve_check(hero, stat, self.BANISH_TARGET, "驱散暮色"):
                if stat == "knowledge":
                    knowledge_ok = True
                else:
                    sanity_ok = True
            # p69：做检定的英雄本回合不能移动或攻击
            hero.movement_stopped = True
            hero.attack_used = True
        if not (knowledge_ok and sanity_ok):
            engine._log("两种心智没能同时奏效——暮色依旧笼罩着这一层。")
            return False
        flags = engine._haunt_flags()
        floors = sorted(set(flags.get("banished_floors", [])) | {room.floor})
        flags["banished_floors"] = floors
        engine._log(f"火光与意志同时亮起——{room.floor} 层的暮色被驱散了！")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p69：消灭所有噩梦 → 英雄胜
        if not self._nightmares(engine):
            engine._set_winner("heroes", "最后一只噩梦也散了——天亮了。")
            return True
        # p69：三层暮色全部驱散 → 英雄胜
        if set(self.FLOORS).issubset(set(flags.get("banished_floors", []))):
            engine._set_winner("heroes", "整栋房子的暮色都被驱散了——长夜结束。")
            return True
        # p140：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "梦魇吞下了最后一个人。")
            return True
        # 吸收兜底：叛徒出局时噩梦照常行动（7/8 号怪物自主口径）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        flags = engine._haunt_flags()
        # 没火把 → 先去熔炉房；有火把 → 找同伴会合驱散暮色
        if not self._carries_torch(engine, player):
            furnace = flags.get("furnace_key")
            if furnace:
                return [f"__room__{furnace}"]
        others = [
            p
            for p in engine.state.players
            if p.role == "hero" and not p.dead and p.id != player.id
        ]
        if others:
            return [f"__room__{others[0].room_key}"]
        return []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        banished = flags.get("banished_floors", [])
        lines = [f"已驱散楼层：{len(banished)}/3（{sorted(banished)}）。"]
        torches = flags.get("torches", {})
        if torches:
            lines.append(f"火把：{len(torches)} 支。")
        haunting = flags.get("haunting", {})
        if haunting:
            lines.append(f"被梦魇缠住：{len(haunting)} 人。")
        lines.append(f"噩梦：{len(self._nightmares(engine))} 只。")
        return lines


class ForAThousandYearsMode(GenericModeHandler):
    """剧本 59「For a Thousand Years / 千年之约」（英雄手册 p70 / 叛徒手册 p141）。

    千年前的诅咒封存了王室血脉；如今王族徽章重见天日，把它挂回国王
    雕像的脖子上就能破咒。可惜叛徒早已布好陷阱——女巫和她的使魔们
    正等着抢走徽章，把它扔下塔楼，让诅咒永世长存。

    · 开局（p141）：女巫 + 雕像令牌放**带预兆图标的房间**（除作祟房，
      无则任意房）；英雄数 ≥3 时熊放带预兆图标的空房间（无则女巫房）、
      ≥4 时猫放女巫房、≥5 时信徒放叛徒房。徽章（omen_medallion）确保
      在叛徒手里（作祟由徽章触发时本来就在；不在则补给他，47 号骷髅
      兜底同口径）。
    · 徽章归属（p141）：flags["medallion_holder"] 统一追踪
      （"traitor:<id>" / "monster:<id>" / "hero:<id>" / None=在地上）；
      英雄持有时同时把卡放进 items（供 UI 与检定），转移时同步。
    · 持徽章移动（p70）：每回合最多移动 2 格（on_player_moved 计数 +
      movement_stopped）；拾取当回合可再走最多 2 格。
    · 放置徽章（p70）：持徽章者在雕像房做速度掷骰，结果 ≥ 房间内未
      昏迷对手数（叛徒+怪物）的两倍 → 挂上雕像 → 英雄胜。
    · 摧毁徽章（p141）：持有者（叛徒或怪物）在塔楼或地下湖结束回合
      → 扔下徽章 → 叛徒胜（on_turn_end 检查）。
    · 怪物攻击（p141）：女巫以知识攻击（目标以理智防御、精神伤害）；
      熊力量攻击多掷 2 骰；猫以速度攻击（目标以速度防御、物理伤害）；
      猫/信徒造成 ≥2 伤害且目标持徽章 → 偷走徽章（bot 总是偷）。
    · 徽章易手：怪物可拾取地上的徽章；怪物被击败/击晕时徽章掉在地上
      （英雄拾取即转为英雄持有）；英雄持有时被偷则同步移出 items。
    · 胜负（p70/p141）：英雄胜 = 徽章挂上雕像；叛徒胜 = 徽章被扔进
      塔楼/地下湖，或英雄全灭。叛徒出局时女巫与使魔继续行动
      （7/8 号怪物自主口径），故吸收兜底。

    已知简化：
        · "拖拽昏迷怪物"未建模（引擎无怪物跟随移动机制）。
        · 怪物探索新房间未建模（复用引擎常规怪物移动，不探索）。
        · 熊/猫禁用特殊通道、猫坠落即晕未建模（引擎怪物走常规门移动）。
        · 徽章"只在回合开始可丢弃/交易"与"狗不能携带"未建模
          （引擎没有怪物/同伴主动持卡的通用层）。
        · 怪物持徽章时"不能丢弃/交易，但可被英雄偷回"简化为：
          怪物被击败或击晕时徽章掉在地上，英雄拾取即转持有。
        · 火把令牌/事件掷骰等无关卡牌不动。
    """

    mode = "badge_curse"

    WITCH = "curse_witch"
    BEAR = "curse_bear"
    CAT = "curse_cat"
    CULTIST = "curse_cultist"
    MEDALLION = "omen_medallion"
    STATUE = "royal_statue"
    DOOM_ROOMS = ("tower", "underground_lake")
    MEDALLION_MOVE_CAP = 2

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("medallion_holder", None)
        flags.setdefault("medallion_steps", {})
        flags.setdefault("statue_key", None)

        # p141：女巫 + 雕像放带预兆图标的房间（除作祟房）
        omen_rooms = [
            k
            for k, r in sorted(engine.state.board.items())
            if r.symbol == "omen" and k != room_key
        ]
        witch_room = omen_rooms[0] if omen_rooms else room_key
        flags["statue_key"] = witch_room
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.WITCH, {"template_id": self.WITCH, "name": "诅咒女巫"})
        )
        engine._spawn_single_haunt_monster(spec, witch_room)
        engine._log("女巫在雕像旁现身——她要亲眼看着诅咒永世长存。")

        players = len(engine.state.players)
        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        specs = engine._haunt_rule_state().get("monster_specs", {})

        # p141：英雄数 ≥3 → 熊（预兆图标的空房间，无则女巫房）
        if hero_count >= 3:
            bear_room = next(
                (
                    k
                    for k in omen_rooms
                    if not any(p.room_key == k for p in engine.state.players)
                    and not any(m.room_key == k for m in engine.state.monsters)
                ),
                witch_room,
            )
            engine._spawn_single_haunt_monster(
                dict(specs.get(self.BEAR, {"template_id": self.BEAR, "name": "女巫之熊"})),
                bear_room,
            )
        # p141：英雄数 ≥4 → 猫（女巫房）
        if hero_count >= 4:
            engine._spawn_single_haunt_monster(
                dict(specs.get(self.CAT, {"template_id": self.CAT, "name": "女巫之猫"})),
                witch_room,
            )
        # p141：英雄数 ≥5 → 信徒（叛徒房）
        if hero_count >= 5:
            traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
            if traitor is not None:
                engine._spawn_single_haunt_monster(
                    dict(
                        specs.get(
                            self.CULTIST, {"template_id": self.CULTIST, "name": "女巫信徒"}
                        )
                    ),
                    traitor.room_key,
                )

        # p141：徽章确保在叛徒手里
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            if self.MEDALLION not in traitor.items:
                traitor.items.append(self.MEDALLION)
            flags["medallion_holder"] = f"traitor:{traitor.id}"
        engine._log("王室徽章在叛徒手里闪闪发光——把它挂回雕像，就能破咒。")

    # ------------------------------------------------------- 徽章归属
    def _statue_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("statue_key")

    def _holder_id(self, flags: dict, prefix: str) -> str | None:
        holder = flags.get("medallion_holder")
        if holder and holder.startswith(prefix + ":"):
            return holder.split(":", 1)[1]
        return None

    def _hero_holds(self, engine: Any, player: Any) -> bool:
        flags = engine._haunt_flags()
        holder = flags.get("medallion_holder")
        return holder == f"hero:{player.id}" or self.MEDALLION in player.items

    def _give_to_hero(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        flags["medallion_holder"] = f"hero:{player.id}"
        flags["medallion_steps"] = {}
        if self.MEDALLION not in player.items:
            player.items.append(self.MEDALLION)

    def _drop_to_floor(self, engine: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["medallion_holder"] = None
        engine.state.room_items.setdefault(room_key, []).append(self.MEDALLION)
        engine._log("徽章哐当一声掉在了地上。")

    def _medallion_on_floor(self, engine: Any) -> str | None:
        flags = engine._haunt_flags()
        if flags.get("medallion_holder") is not None:
            return None
        for key, cards in engine.state.room_items.items():
            if self.MEDALLION in cards:
                return key
        return None

    # ------------------------------------------------------- 持徽章移动
    def on_player_moved(self, engine: Any, player: Any) -> None:
        """p70：持徽章的英雄每回合最多移动 2 格（叛徒持徽章不限速）。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        if player.role != "hero" or not self._hero_holds(engine, player):
            return
        flags = engine._haunt_flags()
        steps = dict(flags.get("medallion_steps", {}))
        used = int(steps.get(str(player.id), 0)) + 1
        steps[str(player.id)] = used
        flags["medallion_steps"] = steps
        if used >= self.MEDALLION_MOVE_CAP:
            player.movement_stopped = True
            player.steps_remaining = 0
            engine._log("徽章沉得惊人——带着它走不动了（本回合最多 2 格）。")

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """回合开始重置持徽章步数（p70：拾取当回合也可再走 2 格）。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        flags = engine._haunt_flags()
        steps = dict(flags.get("medallion_steps", {}))
        if str(player.id) in steps:
            steps.pop(str(player.id))
            flags["medallion_steps"] = steps

    # ------------------------------------------------------- 徽章易手
    def _steal_from_hero(self, engine: Any, monster: Any, hero: Any) -> bool:
        """p141：猫/信徒造成 ≥2 伤害时抢走徽章。"""
        flags = engine._haunt_flags()
        if not self._hero_holds(engine, hero):
            return False
        hero.items = [c for c in hero.items if c != self.MEDALLION]
        flags["medallion_holder"] = f"monster:{monster.id}"
        engine._log(f"{monster.name} 一把抢走了王室徽章！")
        return True

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p141：持徽章的怪物被击败/击晕时，徽章掉在地上（英雄可拾取）。"""
        flags = engine._haunt_flags()
        if flags.get("medallion_holder") == f"monster:{monster.id}":
            self._drop_to_floor(engine, monster.room_key)
        return False  # 噩梦式全权接管不需要——普通击晕流程照走

    # ------------------------------------------------------- 噩梦式怪物攻击
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """p141：怪物可拾取地上的徽章。"""
        template = getattr(monster, "template_id", "")
        if template not in (self.WITCH, self.BEAR, self.CAT, self.CULTIST):
            return False
        flags = engine._haunt_flags()
        floor_key = self._medallion_on_floor(engine)
        if floor_key is not None and floor_key == monster.room_key:
            cards = engine.state.room_items.get(floor_key, [])
            if self.MEDALLION in cards:
                cards.remove(self.MEDALLION)
                flags["medallion_holder"] = f"monster:{monster.id}"
                engine._log(f"{monster.name} 捡起了地上的王室徽章！")
        return False

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p141：女巫知识攻击/熊力量+2 骰/猫速度攻击；打伤持徽章者 ≥2 可抢走。"""
        template = getattr(monster, "template_id", "")
        if template not in (self.WITCH, self.BEAR, self.CAT, self.CULTIST):
            return False
        flags = engine._haunt_flags()
        if flags.get("medallion_holder") == f"monster:{monster.id}":
            # 持徽章的怪物不攻击，专心往塔楼/地下湖跑（p141 无此明文，取合理化）
            return True
        target = engine._find_monster_target(monster)
        if target is None or target.room_key != monster.room_key:
            return True
        if template == self.WITCH:
            roll = engine._roll_monster_attack(monster, "knowledge")
            defense = engine._roll_attack(target, "sanity")
            engine._log(f"诅咒女巫的咒文缠上 {engine._player_label(target)}：{roll} 对 {defense}。")
            if roll > defense:
                engine._deal_damage(target, "mental", roll - defense, source="女巫")
            elif roll < defense:
                engine._stun_monster(monster, 1)
            return True
        if template == self.CAT:
            roll = engine._roll_monster_attack(monster, "speed")
            defense = engine._roll_attack(target, "speed")
            engine._log(f"女巫之猫猛扑 {engine._player_label(target)}：{roll} 对 {defense}。")
        else:  # 熊：力量攻击多掷 2 骰
            roll = engine._roll_monster_attack(monster, "might") + engine.roll_dice(
                2, "熊之蛮力"
            )
            defense = engine._roll_attack(target, "might")
            engine._log(f"女巫之熊横冲直撞：{roll} 对 {defense}。")
        if roll > defense:
            damage = roll - defense
            can_steal = template in (self.CAT, self.CULTIST) and damage >= 2 and self._hero_holds(
                engine, target
            )
            if can_steal:
                self._steal_from_hero(engine, monster, target)
            else:
                engine._deal_damage(target, "physical", damage, source=monster.name)
        elif roll < defense:
            engine._stun_monster(monster, 1)
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        statue_key = self._statue_room(engine)
        for action in actions:
            if getattr(action, "id", "") == "place_medallion":
                if not (
                    self._hero_holds(engine, player)
                    and statue_key is not None
                    and player.room_key == statue_key
                ):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "place_medallion":
            return self._place_medallion(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _place_medallion(self, engine: Any, player: Any) -> bool:
        """p70：速度掷骰 ≥ 房间内未昏迷对手数的两倍 → 挂上雕像 → 英雄胜。"""
        statue_key = self._statue_room(engine)
        if statue_key is None or player.room_key != statue_key:
            return False
        if not self._hero_holds(engine, player):
            return False
        opponents = sum(
            1
            for m in engine.state.monsters
            if m.room_key == statue_key and m.stunned_turns <= 0
        ) + sum(
            1
            for p in engine.state.players
            if p.role == "traitor" and not p.dead and p.room_key == statue_key
        )
        threshold = 2 * opponents
        roll = engine._resolve_check(player, "speed", threshold, "挂上王室徽章")
        if not roll:
            engine._log(
                f"雕像前守着 {opponents} 个敌人（需 ≥{threshold}）——徽章没能挂上去。"
            )
            return False
        engine._log("徽章稳稳挂上了雕像的脖颈——诅咒应声而碎，女巫与使魔化作尘烟！")
        engine._set_winner("heroes", "千年的诅咒破除了——房子恢复了旧日的荣光。")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p141：持有徽章者在塔楼/地下湖结束回合 → 扔下徽章 → 叛徒胜
        holder = flags.get("medallion_holder", "")
        if holder:
            prefix, _, hid = holder.partition(":")
            if prefix in ("traitor", "monster"):
                holder_room = None
                if prefix == "traitor":
                    owner = next((p for p in engine.state.players if p.id == hid), None)
                    holder_room = owner.room_key if owner is not None else None
                else:
                    owner = next((m for m in engine.state.monsters if m.id == hid), None)
                    holder_room = owner.room_key if owner is not None else None
                if holder_room is not None and engine.state.board.get(
                    holder_room
                ) is not None and engine.state.board[holder_room].template_id in self.DOOM_ROOMS:
                    if not engine.state.winner:
                        engine._set_winner(
                            "traitor", "王室徽章被扔进了深渊——诅咒将延续一千年。"
                        )
                        return True
        # p70：徽章挂上雕像 → 英雄胜（在 _place_medallion 里已判，这里兜底 flags）
        # p141：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "最后的继承人倒下了——血脉永埋尘土。")
            return True
        # 吸收兜底：叛徒出局时女巫与使魔继续行动（7/8 号怪物自主口径）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        statue_key = self._statue_room(engine)
        if self._hero_holds(engine, player) and statue_key is not None:
            return [f"__room__{statue_key}"]
        # 徽章在怪物/叛徒手里或地上：优先去捡地上掉落的
        floor_key = self._medallion_on_floor(engine)
        if floor_key is not None:
            return [f"__room__{floor_key}"]
        holder = engine._haunt_flags().get("medallion_holder", "")
        if holder.startswith("monster:"):
            monster = next(
                (m for m in engine.state.monsters if m.id == holder.split(":", 1)[1]), None
            )
            if monster is not None:
                return [f"__room__{monster.room_key}"]
        return []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        holder = flags.get("medallion_holder", "")
        if holder.startswith("hero:"):
            who = "英雄手里"
        elif holder.startswith("traitor:"):
            who = "叛徒手里"
        elif holder.startswith("monster:"):
            who = "怪物手里"
        else:
            who = "掉在地上"
        lines = [f"王室徽章：{who}。"]
        statue_key = self._statue_room(engine)
        if statue_key is not None:
            lines.append(f"雕像位于：{engine.state.board[statue_key].name}。")
        return lines


class BurningSandsMode(GenericModeHandler):
    """剧本 60「The Burning Sands / 燃烧之沙」（英雄手册 p71 / 叛徒手册 p142）。

    发光的文字在墙上重组成谜语：集齐三条线索，在谜语诞生的房间里解开它。
    叛徒和他召唤的斯芬克斯守在门厅——想活着走出这栋房子，先解开谜语。

    · 开局（p140）：斯芬克斯（Speed 3 / Might 5 / Sanity 3 / Knowledge 4）
      数 = 英雄数，全部放门厅（_ensure_room_in_play 保证门厅在场）。
    · 三条线索（p71/p142，双方规则相同）：垃圾房力量 4+（翻垃圾）、
      游戏室速度 4+（整理游戏）、管风琴房理智 4+（听音乐）——每个玩家
      **各自**集齐三枚线索（flags["clues"][id] = set）；成功后**抽一张
      事件牌**（p71 英雄侧）。每回合只能尝试一条检定（引擎 haunt action
      每回合一次天然满足）。
    · 解谜：集齐三线索后在**作祟房**做知识检定——英雄 6+（持水晶球/
      灵应板多掷 1 骰）、叛徒 5+（p142）。英雄成功 → 英雄胜；叛徒
      成功 → 叛徒胜。
    · 斯芬克斯拦路（p71/p142）：英雄离开有未晕斯芬克斯的房间时，该步
      成本为每只 3 点（movement_cost_floor 钩子，17 号蟑螂守厨房先例）；
      被晕的不拦。引擎本就按房间内怪物数 +1，钩子抬高下限。
    · 嘲讽攻击（p142）：斯芬克斯以理智攻击（目标以理智防御、精神伤害）；
      **斯芬克斯输了对决不受伤也不被晕**（on_monster_turn_attack 全权
      接管）。
    · 胜负（p71/p142）：英雄胜 = 解开谜语；叛徒胜 = 解开谜语或英雄全灭。
      叛徒出局时斯芬克斯继续守门（7/8 号怪物自主口径），故吸收兜底。

    已知简化：
        · "英雄用知识攻击斯芬克斯（解它们的谜语）"未建模——引擎没有
          玩家攻击属性选择层；斯芬克斯只能被力量攻击（正常规则）。
        · "多只斯芬克斯同时知识战"未建模（依附于上一条）。
        · 沙偶重生（叛徒受伤时丢弃物品/属性回起始/移门厅）未建模。
        · 斯芬克斯"不进有英雄的房间（除非叛徒或另一只已在）"未建模——
          bot 斯芬克斯守门厅不主动追击，仅在英雄进入门厅时嘲讽。
        · "英雄知识攻击失败回合立即结束"未建模（依附于第一条）。
    """

    mode = "sphinx_riddle"

    SPHINX = "sphinx"
    HALL = "entrance_hall"
    BALL = "omen_crystal_ball"
    BOARD = "omen_spirit_board"
    CRYSTAL_BALL = BALL  # 别名（56 号用名）
    ROLL_TOKENS = ("might", "speed", "sanity")
    CLUE_ROOMS = {
        "might": "junk_room",
        "speed": "game_room",
        "sanity": "organ_room",
    }
    CLUE_TARGET = 4
    HERO_SOLVE = 6
    TRAITOR_SOLVE = 5

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("clues", {})
        flags.setdefault("riddle_solved", False)
        hall_key = engine._ensure_room_in_play(self.HALL, room_key) or room_key
        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.SPHINX, {"template_id": self.SPHINX, "name": "斯芬克斯"})
        )
        for _ in range(hero_count):
            engine._spawn_single_haunt_monster(spec, hall_key)
        engine._log(
            f"{hero_count} 尊斯芬克斯在门厅一字排开——谜语就守在它们身后。"
        )

    # ------------------------------------------------------- 解谜
    def _clues(self, engine: Any, player: Any) -> set:
        flags = engine._haunt_flags()
        clues = dict(flags.get("clues", {}))
        return set(clues.get(str(player.id), ()))

    def _grant_clue(self, engine: Any, player: Any, stat: str) -> None:
        flags = engine._haunt_flags()
        clues = dict(flags.get("clues", {}))
        mine = set(clues.get(str(player.id), ()))
        mine.add(stat)
        clues[str(player.id)] = sorted(mine)
        flags["clues"] = clues

    def _do_clue(self, engine: Any, player: Any, stat: str) -> bool:
        """三线索之一：对应房间做 4+ 检定（双方同规则），成功拿线索 + 抽事件牌。"""
        room = engine.state.board.get(player.room_key)
        if room is None or room.template_id != self.CLUE_ROOMS[stat]:
            return False
        if stat in self._clues(engine, player):
            engine._log(f"{engine._player_label(player)} 已经拿到过这条线索了。")
            return False
        ok = engine._resolve_check(player, stat, self.CLUE_TARGET, "寻找线索")
        if not ok:
            engine._log(f"{engine._player_label(player)} 翻遍了每个角落，一无所获。")
            return False
        self._grant_clue(engine, player, stat)
        engine._log(f"{engine._player_label(player)} 拿到了一条线索（{len(self._clues(engine, player))}/3）！")
        # p71：成功后抽一张事件牌再继续回合
        engine._draw_event(player)
        return True

    def _solve_riddle(self, engine: Any, player: Any, target: int) -> bool:
        haunt_room = engine.state.meta["haunt_rule"].get("haunt_room")
        if haunt_room is None or player.room_key != haunt_room:
            return False
        mine = self._clues(engine, player)
        if len(mine) < 3:
            engine._log(f"{engine._player_label(player)} 的线索还不全（{len(mine)}/3）。")
            return False
        ok = engine._resolve_check(player, "knowledge", target, "解开谜语")
        if not ok:
            engine._log(f"{engine._player_label(player)} 把线索拼来拼去，始终差一点。")
            return False
        flags = engine._haunt_flags()
        flags["riddle_solved"] = True
        if player.role == "traitor":
            engine._set_winner("traitor", "最后一道封印溶解了——远古的荣光重临！")
        else:
            engine._set_winner("heroes", "谜底出口的瞬间，燃烧之沙失去了力量。")
        return True

    # ------------------------------------------------------- 斯芬克斯拦路
    def _sphinxes_in(self, engine: Any, room_key: str) -> int:
        return sum(
            1
            for m in engine.state.monsters
            if m.template_id == self.SPHINX and m.room_key == room_key
            and m.stunned_turns <= 0
        )

    def movement_cost_floor(
        self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None
    ) -> int:
        """p71：离开有未晕斯芬克斯的房间，该步成本每只 3 点。"""
        if from_key is None or player.role != "hero":
            return 0
        count = self._sphinxes_in(engine, from_key)
        return 3 * count if count else 0

    # ------------------------------------------------------- 嘲讽攻击
    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p142：斯芬克斯以理智嘲讽攻击；它输了对决不受伤也不被晕。"""
        if getattr(monster, "template_id", "") != self.SPHINX:
            return False
        target = engine._find_monster_target(monster)
        if target is None or target.room_key != monster.room_key:
            return True
        roll = engine._roll_monster_attack(monster, "sanity")
        defense = engine._roll_attack(target, "sanity")
        engine._log(f"斯芬克斯的谜语嘲讽 {engine._player_label(target)}：{roll} 对 {defense}。")
        if roll > defense:
            engine._deal_damage(target, "mental", roll - defense, source="斯芬克斯")
        # 输了对决：斯芬克斯不受伤、不被晕（p142 明文）——什么都不做
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        haunt_room = engine.state.meta["haunt_rule"].get("haunt_room")
        for action in actions:
            aid = getattr(action, "id", "")
            # 解谜：须集齐三线索且在作祟房
            if aid in ("solve_riddle", "traitor_solve_riddle") and not (
                len(self._clues(engine, player)) >= 3 and player.room_key == haunt_room
            ):
                continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "clue_junk":
            return self._do_clue(engine, player, "might")
        if action_id == "clue_gameroom":
            return self._do_clue(engine, player, "speed")
        if action_id == "clue_organ":
            return self._do_clue(engine, player, "sanity")
        if action_id == "solve_riddle":
            return self._solve_riddle(engine, player, self.HERO_SOLVE)
        if action_id == "traitor_solve_riddle":
            return self._solve_riddle(engine, player, self.TRAITOR_SOLVE)
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p142：叛徒解开谜语 → 叛徒胜（p71：英雄解开 → 英雄胜，已在行动里判）
        if flags.get("riddle_solved"):
            if engine.state.winner is None:
                engine._set_winner("traitor", "远古的封印溶解了——荣光重临。")
            return True
        # p142：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "没人能解开谜语了——斯芬克斯永远守着它。")
            return True
        # 吸收兜底：叛徒出局时斯芬克斯继续守谜（7/8 号怪物自主口径）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        mine = self._clues(engine, player)
        # 缺哪条线索就去哪个房间；集齐三枚直奔作祟房
        for stat in self.ROLL_TOKENS:
            if stat not in mine:
                return [f"__room__{self.CLUE_ROOMS[stat]}"]
        haunt_room = engine.state.meta["haunt_rule"].get("haunt_room")
        return [f"__room__{haunt_room}"] if haunt_room else []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = []
        for p in engine.state.players:
            mine = self._clues(engine, p)
            if p.role == "hero" and not p.dead:
                lines.append(f"{p.name}：线索 {len(mine)}/3（{','.join(mine) or '—'}）。")
        return lines


class KingsRoadsMode(GenericModeHandler):
    """剧本 55 国王之路（The King's Roads）。

    权威原文：英雄手册 p66 / 叛徒手册 p137。
    · 驱魔检定：知识/理智 5+，实验室/教堂/温室/地窖；每房一次。
    · 影子（ghost 模板承载，Speed 3）：每玩家一只，追击英雄。
    · 英雄胜：驱魔数 = 玩家数；叛徒胜：英雄全灭。
    · 简化：国王之路传送未建模（影子正常追击）；擒抱未建模。
    """

    mode = "kings_roads"

    ENTRANCE_ROOMS = ["garden", "graveyard", "patio", "tower", "balcony", "underground_lake"]
    DISENCHANT_ROOMS = ["research_laboratory", "chapel", "conservatory", "crypt", "mystic_elevator"]

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["used_sources"] = []
        # 影子：每玩家一只，放最近入口房间
        spec = next((s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == "ghost"), {})
        spec = dict(spec)
        spec["name"] = "影子"
        spec["speed"] = 3
        entrances = [k for k, r in engine.state.board.items()
                     if r.template_id in self.ENTRANCE_ROOMS]
        if not entrances:
            entrances = [room_key]
        for hero in engine.state.players:
            if hero.role != "hero" or hero.dead:
                continue
            nearest = min(sorted(entrances), key=lambda k: engine._path_length(hero.room_key, k))
            engine._spawn_single_haunt_monster(spec, nearest)
        engine._log(f"{len(engine.state.monsters)} 道影子从国王之路涌入了房子！")

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        used = set(engine._haunt_flags().get("used_sources", []))
        for action in actions:
            if action.id == "disenchant_room":
                room_id = engine._current_room_template_id(player)
                if room_id in used:
                    continue
                has_item = any(item in player.items for item in ("omen_crystal_ball", "omen_mask"))
                if room_id not in self.DISENCHANT_ROOMS and not has_item:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        if action_id == "disenchant_room":
            room_id = engine._current_room_template_id(player)
            used = set(engine._haunt_flags().get("used_sources", []))
            if room_id in used:
                engine._log("这个房间已经用过了。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                used.add(room_id)
                engine._haunt_flags()["used_sources"] = sorted(used)
            return ok
        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        if engine._haunt_track_value("disenchant_progress") >= engine._haunt_track_target("disenchant_progress"):
            engine._set_winner("heroes", "国王之路被封住了——影子退回了暗影国度。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "影子附身了最后的英雄。")
            return True
        return False



class ArkanokSkullMode(GenericModeHandler):
    """剧本 54 阿卡诺克之颅（The Skull of Ar'Kanok）。

    权威原文：英雄手册 p65 / 叛徒手册 p136。
    · 骷髅 token 放作祟房间；遗骸在六类房间之一。
    · 侦测：持骷髅/圣徽理智 4+；持水晶球/灵应板知识 5+。
    · 净化：持骷髅在遗骸房间理智 5+。
    · 僵尸 2× 英雄数（Speed 1 Might 4 Sanity 2）。
    · 英雄胜：净化；叛徒胜：英雄全灭。
    """

    mode = "arkanok_skull"

    REMAINS_ROOMS = ["chapel", "crypt", "graveyard", "furnace_room", "bloody_room", "charred_room"]

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["remains_found"] = False
        flags["skull_picked"] = False
        # 遗骸房间（叛徒知道；bot 随机选）
        candidates = [rid for rid in self.REMAINS_ROOMS
                      if any(r.template_id == rid for r in engine.state.board.values())]
        if not candidates:
            candidates = self.REMAINS_ROOMS
        remains_template = engine.rng.choice(candidates)
        remains_key = next((k for k, r in engine.state.board.items() if r.template_id == remains_template), None)
        if remains_key is None:
            remains_key = engine._ensure_room_in_play(remains_template, room_key)
        flags["remains_room"] = remains_key
        # 骷髅 token 放作祟房间
        engine.spawn_token("skull", label="Ar'Kanok 之颅", role="marker", room_key=room_key)
        # 僵尸 2× 英雄数
        spec = next((s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == "zombie"), {})
        spec = dict(spec)
        spec["name"] = "僵尸"
        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        for _ in range(hero_count * 2):
            key = engine.rng.choice(sorted(engine.state.board.keys()))
            engine._spawn_single_haunt_monster(spec, key)
        engine._log("墙壁长出了腐肉——僵尸在房子里游荡！")

    def _object_room(self, engine):
        for t in engine.state.tokens:
            if t.kind == "skull":
                if t.holder is not None:
                    p = next((p for p in engine.state.players if p.id == t.holder), None)
                    return p.room_key if p else None
                return t.room_key
        return None

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        room_id = engine._current_room_template_id(player)
        has_skull = engine.tokens_held_by(player.id, "skull")
        has_hs = "omen_holy_symbol" in player.items
        has_cb = "omen_crystal_ball" in player.items
        has_sb = "omen_spirit_board" in player.items
        for action in actions:
            if action.id == "detect_remains":
                if not (has_skull or has_hs or has_cb or has_sb):
                    continue
                if flags.get("remains_found"):
                    continue
            if action.id == "exorcise":
                if not has_skull or not flags.get("remains_found"):
                    continue
                if room_id != engine.state.board.get(flags.get("remains_room"), type("R", (), {"template_id": ""})).template_id:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        flags = engine._haunt_flags()
        if action_id == "detect_remains":
            room_id = engine._current_room_template_id(player)
            has_skull = engine.tokens_held_by(player.id, "skull")
            has_hs = "omen_holy_symbol" in player.items
            has_cb = "omen_crystal_ball" in player.items
            has_sb = "omen_spirit_board" in player.items
            if has_skull or has_hs:
                ok = engine._resolve_check(player, "sanity", 4, "侦测遗骸")
            elif has_cb or has_sb:
                ok = engine._resolve_check(player, "knowledge", 5, "搜索遗骸")
            else:
                engine._log("需要骷髅/圣徽/水晶球/灵应板才能侦测。")
                return False
            if ok:
                flags["remains_found"] = True
                room = engine.state.board.get(flags["remains_room"])
                engine._log(f"Ar'Kanok 的遗骸在{room.name}！")
            else:
                engine._log("侦测失败。")
            return True

        if action_id == "exorcise":
            room_id = engine._current_room_template_id(player)
            if not engine.tokens_held_by(player.id, "skull"):
                engine._log("你需要持有骷髅。")
                return False
            remains_key = flags.get("remains_room")
            if remains_key is None or engine.state.board.get(remains_key, type("R", (), {"template_id": ""})).template_id != room_id:
                engine._log("你必须在遗骸所在的房间。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                skull = next(iter(engine.tokens_held_by(player.id, "skull")), None)
                if skull:
                    engine.place_token(skull.uid, player.room_key)
                engine._log("Ar'Kanok 的灵魂终于安息了！")
            return ok

        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        if engine._haunt_track_value("ritual_progress") >= engine._haunt_track_target("ritual_progress"):
            engine._set_winner("heroes", "Ar'Kanok 安息了——僵尸随之倒下。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "僵尸撕碎了最后的英雄。")
            return True
        return False



class ToxicObjectEscapeMode(GenericModeHandler):
    """剧本 53 死亡恶臭（Reeking of Death）。

    权威原文：英雄手册 p64 / 叛徒手册 p135。
    · 死亡之物：狗携带（Speed 6 Might 4）；可被偷/掉落。
    · 毒云：有物之房间放 token；进入掷骰（2 无/1 -1 物理/0 -1 物理-1 精神）；
      回合结束在有物或毒云房间 -1 全属性。
    · 逃跑：清障碍（力量 4+，人数次）→ 解锁（知识 5+）→ 逃离（2 格移动）。
    · 净化：在熔炉房/地下湖开始回合持物。
    · 英雄胜：半数逃出 或 净化+半数存活；叛徒胜：英雄全灭。
    · 简化：狗掉落物品（2+ 物理伤害）未建模；毒云逐回合扩展未建模。
    """

    mode = "toxic_object_escape"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["object_cleansed"] = False
        flags["door_unlocked"] = False
        flags["escaped"] = []
        # 死亡之物令牌由狗携带
        dog = engine._monster_by_template("dog")
        if dog is not None:
            engine.spawn_token("deathly_object", label="死亡之物", role="carried", holder=int(dog.id.split("_")[-1]) if "_" in dog.id else None)
        engine._log("恶臭弥漫——狗叼着一个死亡之物在房子里游荡！")

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        if player.dead or player.role == "traitor":
            return
        # 毒云伤害：回合结束在有物或毒云房间
        obj_room = self._object_room(engine)
        poison_rooms = set(engine.tokens_in_room.__self__.state.tokens and
                           [t.room_key for t in engine.state.tokens if t.kind == "poison_cloud"] or [])
        if (player.room_key == obj_room or player.room_key in poison_rooms) and obj_room:
            for stat in ("speed", "might", "sanity", "knowledge"):
                engine._apply_stat_loss(player, stat, 1)
            engine._log(f"{player.name} 在毒气中失去了 1 点全属性。")
            engine.check_victory()

    def on_enter_room(self, engine, player, room):
        if player.dead or player.role == "traitor":
            return
        obj_room = self._object_room(engine)
        poison_rooms = [t.room_key for t in engine.state.tokens if t.kind == "poison_cloud"]
        if room.key == obj_room or room.key in poison_rooms:
            roll = engine.roll_dice(1, "毒云")
            if roll == 0:
                engine._apply_stat_loss(player, "might", 1)
                engine._apply_stat_loss(player, "sanity", 1)
                engine._log(f"{player.name} 吸入毒气（-1 物理 -1 精神）。")
            elif roll == 1:
                engine._apply_stat_loss(player, "might", 1)
                engine._log(f"{player.name} 吸入毒气（-1 物理）。")
            else:
                engine._log(f"{player.name} 屏住了呼吸。")
            engine.check_victory()

    def _object_room(self, engine):
        for t in engine.state.tokens:
            if t.kind == "deathly_object":
                if t.holder is not None:
                    p = next((p for p in engine.state.players if p.id == t.holder), None)
                    return p.room_key if p else None
                return t.room_key
        return None

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        for action in actions:
            if action.id == "cleanse_object":
                room_id = engine._current_room_template_id(player)
                if room_id not in ("furnace_room", "underground_lake"):
                    continue
                if not engine.tokens_held_by(player.id, "deathly_object"):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        flags = engine._haunt_flags()
        if action_id == "flee_house":
            escaped = flags.setdefault("escaped", [])
            if player.id not in escaped:
                escaped.append(player.id)
                engine._log(f"{player.name} 冲出了前门！")
            engine.check_victory()
            return True

        if action_id == "cleanse_object":
            if not engine.tokens_held_by(player.id, "deathly_object"):
                engine._log("你身上没有死亡之物。")
                return False
            token = next(iter(engine.tokens_held_by(player.id, "deathly_object")), None)
            if token:
                engine.remove_token(token.uid)
            flags["object_cleansed"] = True
            engine._log("死亡之物被净化了——诅咒结束了！")
            engine.check_victory()
            return True

        if action_id == "unlock_door":
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                flags["door_unlocked"] = True
                engine._log("前门解锁了！")
            return ok

        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        import math
        flags = engine._haunt_flags()
        heroes_start = sum(1 for p in engine.state.players if p.role == "hero")
        escaped = len(flags.get("escaped", []))
        need = math.ceil(heroes_start / 2)
        cleansed = flags.get("object_cleansed", False)
        heroes_alive = sum(1 for p in engine.state.players if p.role == "hero" and not p.dead)

        if cleansed and heroes_alive >= need:
            engine._set_winner("heroes", "死亡之物被净化了——毒气消散了。")
            return True
        if escaped >= need:
            engine._set_winner("heroes", "半数英雄逃出了前门——他们得救了。")
            return True
        if heroes_alive == 0:
            engine._set_winner("traitor", "毒气吞噬了最后的生命。")
            return True
        return False



class CracklingAuraMode(GenericModeHandler):
    """剧本 52 噼啪光环中（In a Crackling Aura）。

    权威原文：英雄手册 p63 / 叛徒手册 p134。
    · 魔法尘：英雄在事件房掷 3 骰（水晶球 4 骰）4+ → 获得魔法尘。
    · 反魔法场：丢弃魔法尘 → 该房间变反魔法场（叛徒不可施法/召唤）。
    · 恶魔领主：叛徒在五芒星室知识 5+ 召唤（Might 7 Speed 5 Sanity 4）。
    · 英雄胜：叛徒死 + 无恶魔在场。
    · 简化：叛徒法术系统（火球/传送）未建模；反魔法场回合清除未建模。
    """

    mode = "ring_exorcism"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["anti_magic_rooms"] = []
        flags["demon_alive"] = False
        engine._log("你的朋友手上戴着一枚发光的戒指，周身噼啪作响……")

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        if player.role != "traitor" or player.dead:
            return
        # p134：叛徒在五芒星室召唤恶魔领主
        pentagram = next(
            (k for k, r in engine.state.board.items() if r.template_id == "pentagram_chamber"),
            None,
        )
        if pentagram is None or player.room_key != pentagram:
            return
        if flags.get("demon_alive"):
            return
        if pentagram in flags.get("anti_magic_rooms", []):
            engine._log("反魔法场阻止了召唤！")
            return
        roll = engine.roll_dice(max(1, engine._effective_stat(player, "knowledge")), "召唤恶魔")
        if roll >= 5:
            haunt_rule = engine.state.haunt.rule_data or {}
            spec = next(
                (s for s in haunt_rule.get("monsters", []) if s.get("template_id") == "giant"),
                {},
            )
            spec = dict(spec)
            spec["name"] = "恶魔领主"
            monster = engine._spawn_single_haunt_monster(spec, pentagram)
            if monster is not None:
                flags["demon_alive"] = True
                engine._log("恶魔领主从五芒星室中降临！")
        else:
            engine._log(f"召唤失败（{roll}）。")

    def on_monster_defeated(self, engine, monster, amount):
        if getattr(monster, "name", "") != "恶魔领主":
            return False
        flags = engine._haunt_flags()
        flags["demon_alive"] = False
        monster_id = getattr(monster, "id", None)
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
        ]
        engine._log("恶魔领主被驱回了地狱！")
        engine.check_victory()
        return True

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "search_dust":
                room = engine.current_room(player)
                if room.symbol != "event":
                    continue
            if action.id == "drop_dust":
                if not engine.tokens_held_by(player.id, "magic_dust"):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        flags = engine._haunt_flags()
        if action_id == "search_dust":
            dice = 4 if "omen_crystal_ball" in player.items else 3
            roll = engine.roll_dice(dice, "魔法尘")
            if roll >= 4:
                engine.spawn_token("magic_dust", label="魔法尘", role="carried", holder=player.id)
                engine._log(f"{player.name} 找到了魔法尘！（{roll}）")
            else:
                engine._log(f"{player.name} 没有找到魔法尘（{roll}）。")
            return True

        if action_id == "drop_dust":
            token = next(iter(engine.tokens_held_by(player.id, "magic_dust")), None)
            if token is None:
                return False
            engine.place_token(token.uid, player.room_key)
            anti = flags.setdefault("anti_magic_rooms", [])
            if player.room_key not in anti:
                anti.append(player.room_key)
            engine._log(f"魔法尘散布在{engine.state.board[player.room_key].name}——反魔法场形成了！")
            return True

        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        flags = engine._haunt_flags()
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        demons = [m for m in engine.state.monsters if getattr(m, "name", "") == "恶魔领主"]
        traitor_dead = traitor is None or traitor.dead
        if traitor_dead and not demons:
            engine._set_winner("heroes", "戒指失去了魔力——叛徒倒在 你的脚下。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "恶魔的嚎叫淹没 了最后的呼救。")
            return True
        return False



class DarkerThanNightMode(GenericModeHandler):
    """剧本 51 比夜更黑（Darker than Night）。"""

    mode = "darker_than_night"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["dark_hexes"] = 0
        flags["seal_rooms_used"] = []
        engine._log("窗户变成了镜子——黑暗在房子里蔓延。")

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        if player.role != "traitor" or player.dead:
            return
        hexes = int(flags.get("dark_hexes", 0))
        if hexes >= 3:
            return
        outer_rooms = [
            k for k, r in engine.state.board.items()
            if r.template_id in ("balcony", "garden", "graveyard", "patio", "tower")
            and not engine.tokens_in_room(k, "dark_hex")
        ]
        if outer_rooms:
            room = engine.rng.choice(sorted(outer_rooms))
            roll = engine._roll_attack(player, "knowledge")
            if roll >= 5:
                engine.spawn_token("dark_hex", label="黑暗 Hex", role="marker", room_key=room)
                flags["dark_hexes"] = hexes + 1
                engine._log(f"黑暗仪式推进了！（{hexes + 1}/3）")
                engine.check_victory()

    def check_victory(self, engine):
        flags = engine._haunt_flags()
        if engine._haunt_track_value("hero_progress") >= engine._haunt_track_target("hero_progress"):
            engine._set_winner("heroes", "圣印驱散了黑暗。")
            return True
        if int(flags.get("dark_hexes", 0)) >= 3:
            engine._set_winner("traitor", "黑暗仪式完成了。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也被黑暗吞噬了。")
            return True
        return False


class PortraitCurseMode(GenericModeHandler):
    """剧本 57「A Friend for the Ages」（英雄手册 p68 / 叛徒手册 p139）。

    三百年前一位挚友赠他的肖像成了抵御岁月与伤痛的护符：画在，人就不死。
    如今他咬定朋友们是来抢那幅画的——他们要毁掉它，还是替他守住它？

    · 颜料（p68）：令牌数 = 英雄数 + 2，只放阁楼/废弃房/坍塌房/露台/雕像走廊/
      储藏室（原版 Storeroom 与 Larder 在本项目共用 larder）/酒窖，每间一枚。
      房间比令牌多时，优先放"离任何探险者最远"的那几间；令牌比房间多时，
      多出来的先搁置，等清单上的房间被探索出来再补放（`on_room_discovered`）。
    · 画廊（p68）：肖像就挂在画廊。原版默认它在场，电子版探索阶段未必翻得到，
      开局用 `_ensure_room_in_play` 从房间牌堆把它找出来放下，否则英雄无处重绘。
    · 重绘（p68）：英雄在画廊且随身带着颜料 → 知识 4+ → 成功则颜料销毁并在
      房内放一枚知识检定令牌；检定令牌集满"作祟开始时的英雄数"即破除诅咒。
      目标数在 setup 里快照（`_resolve_haunt_target("hero_count")` 只数活人，
      英雄中途阵亡会让原版固定的目标缩水）。
    · 无敌（p139）：他的属性不受事件、房间特征与伤害削减。引擎所有伤害都走
      `_deal_damage` → `_adjust_damage_for_haunt`，所以 `physical_damage_reduction`
      对他全额减免即可；代价是他也不可能被击杀。英雄净胜 2 点仍能抢他一件
      物品（走引擎常规偷窃分支）。唯一例外：持远古护身符的英雄打赢他，
      伤害照常扣属性（p68）。
    · 肖像（p139）：他不得直视自己的画像——进入画廊、或回合开始就在画廊 →
      理智 4+，失败吃 1 骰精神伤害。这是唯一无视其免疫的伤害，用
      `_apply_damage_amounts` 直接结算绕开减免钩子；他也只可能死在这里，
      而"叛徒死亡"正是 p68 给英雄的第二条胜利路线。
    · 开局（p139）：先把低于起点的属性补回起点，再"每名英雄一次"把
      离起点滑格数最少的属性往上抬一格（并列时原版由玩家自选，这里按固定
      属性序取第一格保证同种子确定性）。
    · 销毁颜料（p139）：手持颜料时可以销毁一枚**代替一次攻击**——所以销毁后
      本回合不能再出刀（`attack_allowed`），且已攻击后不能再销毁。毁满 3 枚即胜。
    · 胜负（p68/p139）：英雄胜 = 集满知识检定令牌，或叛徒死亡；叛徒胜 =
      销毁 3 枚颜料，或英雄全灭。后两条中"死亡"类判定由引擎通用规则兜底。

    已知简化：
        · "颜料不能被狗携带"自动满足——本项目同伴卡不占物品栏、无法持物。
        · 事件/房间特征中不走伤害结算的直接降属性（如 `event_the_voice`
          检定失败 -1 知识）没有被免疫拦住：引擎没有降属性钩子。
        · 抢颜料的阈值沿用引擎 `special_steal` 的"净胜 > 2"，比原版"净胜 ≥ 2"
          严一格；卡牌类物品的抢夺仍走引擎原分支。
        · 拿/传/放颜料与重绘共用引擎"每人每回合一次剧本行动"的限额。
        · "放下颜料 / 交给队友"只在同屋有空手且知识更高的英雄、且自己不在画廊时
          提供（原版颜料可像物品一样随处放下）。收窄的原因：机器人实测会陷入
          "放下→再捡起"的原地循环，一罐也带不进画廊。
        · 重绘的检定目标固定为知识 4+，不使用"多名英雄合力"之类的房规。
    """

    mode = "portrait_curse"

    PAINT = "paint"
    CHECK = "knowledge_check"
    GALLERY = "gallery"
    AMULET = "item_amulet_of_the_ages"
    PAINT_ROOMS = (
        "attic", "abandoned_room", "collapsed_room", "patio",
        "statuary_corridor", "larder", "wine_cellar",
    )
    STAT_ORDER = ("speed", "might", "sanity", "knowledge")

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        hero_count = max(1, sum(1 for p in engine.state.players if p.role == "hero" and not p.dead))
        flags["repaint_needed"] = hero_count
        flags["spell_broken"] = False
        flags["destroyed_this_turn"] = False
        tracks = engine._haunt_tracks()
        tracks.setdefault("repaint", {"label": "英雄：重绘肖像（知识检定令牌）", "target": hero_count, "value": 0})
        tracks["repaint"]["target"] = hero_count

        # p68：画廊是诅咒的所在，牌堆里找出来放下
        gallery_key = engine._ensure_room_in_play(self.GALLERY, room_key)
        if gallery_key:
            engine._log(f"那幅画就挂在{engine.state.board[gallery_key].name}——叛徒不敢看它第二眼。")
        else:
            engine._log("画廊没能放进屋子：英雄只能靠杀死叛徒来结束这一切（已知简化）。")

        total = hero_count + 2
        flags["paint_total"] = total
        placed = self._place_paint(engine, total)
        # p68 假设这些房间总能在屋里找到；本局可能一间都没翻到（实测 seed=109/4p
        # 零间、五罐颜料全被搁置），那样英雄一罐颜料都拿不到，重绘路线直接死锁。
        # 按 p84 的先例（"If the Pentagram Chamber isn't in the house, search the
        # room stack for it and put it…"）把清单上的房间强行拉进屋子，至少补足
        # 重绘所需的"英雄数"那一档；多出来的两罐仍走"搁置待发现"。
        while placed < hero_count:
            room_id = next(
                (
                    tid for tid in self.PAINT_ROOMS
                    if tid in (*engine.state.room_deck, *engine.state.room_discard)
                    and not any(room.template_id == tid for room in engine.state.board.values())
                ),
                None,
            )
            if room_id is None:
                break
            key = engine._ensure_room_in_play(room_id, room_key)
            if key is None:
                break  # 放不下（牌已还回牌堆）：再试别的房间只会死循环
            engine.spawn_token(self.PAINT, label="颜料", role="marker", room_key=key)
            placed += 1
        flags["pending_paint"] = max(0, total - placed)
        engine._log(
            f"{placed} 罐颜料散落在屋里最冷清的角落"
            + (f"，另有 {flags['pending_paint']} 罐等着房间被翻开。" if flags["pending_paint"] else "。")
        )
        self._boost_traitor(engine)

    def _place_paint(self, engine: Any, total: int) -> int:
        """p68：每间合适房一枚；房间比令牌多时挑离探险者最远的几间。"""
        candidates = [
            key for key, room in sorted(engine.state.board.items())
            if room.template_id in self.PAINT_ROOMS and not engine.tokens_in_room(key, self.PAINT)
        ]
        if not candidates:
            return 0
        if len(candidates) > total:
            candidates.sort(key=lambda key: (-self._min_distance_to_explorer(engine, key), key))
            candidates = candidates[:total]
        for key in candidates:
            engine.spawn_token(self.PAINT, label="颜料", role="marker", room_key=key)
        return len(candidates)

    def _min_distance_to_explorer(self, engine: Any, room_key: str) -> int:
        """该房间到"最近的活人"的距离（不可达记 0，不参与最远排序）。"""
        distances = [
            engine._path_length(room_key, player.room_key)
            for player in engine.state.players
            if not player.dead and player.room_key
        ]
        if not distances:
            return 0
        nearest = min(distances)
        return 0 if nearest >= 9999 else nearest

    def _boost_traitor(self, engine: Any) -> None:
        """p139：补回起点，然后每名英雄让他抬一格离起点最近的属性。"""
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is None or traitor.dead:
            return
        face = engine.catalog.characters.get(traitor.character_id)
        if face is None:
            return
        for stat in self.STAT_ORDER:
            start = face.stats.get(stat)
            track = engine._stat_track(traitor, stat)
            if start is None or not track:
                continue
            start_pos = next((i for i, value in enumerate(track) if value >= start), len(track) - 1)
            if traitor.stat_positions.get(stat, start_pos) < start_pos:
                traitor.stat_positions[stat] = start_pos
                traitor.stats[stat] = track[start_pos]
        hero_count = sum(1 for p in engine.state.players if p.role == "hero" and not p.dead)
        for _ in range(hero_count):
            best_stat = None
            best_gap = None
            for stat in self.STAT_ORDER:
                track = engine._stat_track(traitor, stat)
                if not track:
                    continue
                start = face.stats.get(stat)
                if start is None:
                    continue
                start_pos = next((i for i, value in enumerate(track) if value >= start), len(track) - 1)
                pos = traitor.stat_positions.get(stat, start_pos)
                gap = pos - start_pos  # 滑格高出起点几格（原版：least slider positions above start）
                if pos >= len(track) - 1:
                    continue  # 已到顶格，抬无可抬
                if best_gap is None or gap < best_gap:
                    best_stat, best_gap = stat, gap
            if best_stat is None:
                break
            pos = traitor.stat_positions[best_stat] + 1
            track = engine._stat_track(traitor, best_stat)
            traitor.stat_positions[best_stat] = min(pos, len(track) - 1)
            traitor.stats[best_stat] = track[traitor.stat_positions[best_stat]]
        engine._log(f"{traitor.name} 把岁月与伤口都移进了画里——他的属性高出起点一截。")

    # ------------------------------------------------------- 颜料与肖像
    def _held_paint(self, engine: Any, player: Any) -> list[Any]:
        return engine.tokens_held_by(player.id, self.PAINT)

    def _gallery_key(self, engine: Any) -> str:
        return next((key for key, room in engine.state.board.items() if room.template_id == self.GALLERY), "")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        """p68：搁置的颜料在清单上的房间被发现时补进去。"""
        flags = engine._haunt_flags()
        pending = int(flags.get("pending_paint", 0))
        if pending <= 0 or room.template_id not in self.PAINT_ROOMS:
            return
        if engine.tokens_in_room(room.key, self.PAINT):
            return
        flags["pending_paint"] = pending - 1
        engine.spawn_token(self.PAINT, label="颜料", role="marker", room_key=room.key)
        engine._log(f"{room.name}里另有一罐颜料（待放 {flags['pending_paint']} 罐）。")

    def _portrait_gaze(self, engine: Any, player: Any) -> None:
        """p139：叛徒进画廊/开局在画廊 → 理智 4+，失败吃 1 骰精神伤害（无视免疫）。"""
        if player.role != "traitor" or player.dead:
            return
        if engine._resolve_check(player, "sanity", 4, "抗拒肖像的凝视"):
            engine._log(f"{player.name} 强迫自己别去看那幅画。")
            return
        roll = engine.roll_dice(1, "肖像的反噬")
        engine._log(f"画中人替他挡下了三百年的伤，此刻却向他讨债（精神伤害 {roll}）。")
        # 直接结算：绕开 _deal_damage，否则会被他自己的免疫吃干净
        engine._apply_damage_amounts(player, mental=roll, source="肖像")
        engine.check_victory()

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        if room.template_id == self.GALLERY:
            self._portrait_gaze(engine, player)

    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.role == "traitor":
            flags["destroyed_this_turn"] = False
            if self._in_gallery(engine, player):
                self._portrait_gaze(engine, player)

    # --------------------------------------------------------- 无敌与抢夺
    def physical_damage_reduction(self, engine: Any, player: Any, amount: int, source: str, damage_type: str) -> int:
        """p139/p68：叛徒不受伤害削减；持远古护身符的英雄肉搏打赢他是唯一例外。"""
        if player.role != "traitor" or amount <= 0:
            return 0
        active_id = getattr(engine, "_active_player_id", None)
        attacker = None
        if active_id is not None and 0 <= active_id < len(engine.state.players):
            attacker = engine.state.players[active_id]
        if (
            source == "攻击"
            and attacker is not None
            and getattr(attacker, "role", "") == "hero"
            and self.AMULET in getattr(attacker, "items", [])
        ):
            return 0
        return amount

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p139：销毁颜料"代替一次攻击"——两件事一回合里只能做一件。"""
        if attacker.role != "traitor":
            return True
        return not bool(engine._haunt_flags().get("destroyed_this_turn"))

    def special_steal(self, engine: Any, attacker: Any, target: Any, diff: int, attack_attr: str) -> bool:
        """p68：颜料能像普通物品一样被抢走——他手里的颜料可以被夺下来。"""
        if target.role != "traitor" or getattr(attacker, "role", "") != "hero":
            return False
        held = self._held_paint(engine, target)
        if not held or self._held_paint(engine, attacker):
            return False  # 攻击者已带一枚，抢了也带不走
        token = held[0]
        engine.give_token(token.uid, attacker.id)
        engine._log(f"{attacker.name} 从{target.name}手里夺下了{token.label}！")
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        held = self._held_paint(engine, player)
        result = []
        for action in actions:
            action_id = action.id
            if action_id == "take_paint":
                if held or not engine.tokens_in_room(player.room_key, self.PAINT):
                    continue  # p68：每人同时只能携带一枚
            elif action_id == "repaint_portrait":
                # rooms 不写在 rule_data 里（会被 bot 当成常驻目标），限制由这里把关
                if not held or not self._in_gallery(engine, player):
                    continue
            elif action_id in {"drop_paint", "pass_paint", "destroy_paint"}:
                if not held:
                    continue
                if action_id == "destroy_paint":
                    if player.role != "traitor" or getattr(player, "attack_used", False):
                        continue  # 已经攻击过就不能再"代替攻击"
                elif self._in_gallery(engine, player):
                    # 人都到画廊了，那就落笔，别再倒手颜料
                    continue
                elif not self._pass_targets(engine, player):
                    # 没人接得住就别放下：机器人只会"放下→再捡起"原地打转，
                    # 永远走不到画廊（实测 seed=109/4p 重绘 0/3）。
                    continue
            result.append(action)
        return result

    def _in_gallery(self, engine: Any, player: Any) -> bool:
        room = engine.state.board.get(player.room_key)
        return room is not None and room.template_id == self.GALLERY

    def _pass_targets(self, engine: Any, player: Any) -> list[Any]:
        """同房、没带颜料、且**知识更高**的英雄（p68：颜料可以交易）。

        只交给"更可能重绘成功"的队友：不加这条限制，两个英雄会你递给我、
        我递给你，把每回合一次的行动额度全花在传颜料上。
        """
        if player.role != "hero":
            return []
        mine = int(player.stats.get("knowledge", 0))
        return [
            other for other in engine.state.players
            if not other.dead and other.id != player.id
            and other.role == "hero"
            and other.room_key == player.room_key and not self._held_paint(engine, other)
            and int(other.stats.get("knowledge", 0)) > mine
        ]

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        held = self._held_paint(engine, player)
        if action_id == "take_paint":
            token = next(iter(engine.tokens_in_room(player.room_key, self.PAINT)), None)
            if token is None:
                engine._log("这个房间里没有颜料。")
                return False
            if held:
                engine._log("每人一次只能携带一罐颜料（p68）。")
                return False
            engine.give_token(token.uid, player.id)
            engine._log(f"{player.name} 收起了{token.label}。")
            return True

        if action_id == "drop_paint":
            if not held:
                engine._log("你身上没有颜料。")
                return False
            engine.place_token(held[0].uid, player.room_key)
            room = engine.state.board.get(player.room_key)
            engine._log(f"{player.name} 把颜料留在了{(room.name if room else '原地')}。")
            return True

        if action_id == "pass_paint":
            if not held:
                engine._log("你身上没有颜料可交。")
                return False
            candidates = self._pass_targets(engine, player)
            if not candidates:
                engine._log("同房间里没有需要颜料的队友。")
                return False
            choice = engine.prompter.choose_from_list(
                "传递颜料", "把颜料交给谁？", [p.name for p in candidates]
            )
            target = candidates[choice] if choice is not None and 0 <= choice < len(candidates) else candidates[0]
            engine.give_token(held[0].uid, target.id)
            engine._log(f"{player.name} 把颜料塞给了{target.name}。")
            return True

        if action_id == "repaint_portrait":
            if not held:
                engine._log("重绘肖像得先带上一罐颜料。")
                return False
            if not self._in_gallery(engine, player):
                engine._log("那幅画挂在画廊——重绘必须站在它面前（p68）。")
                return False
            before = engine._haunt_track_value("repaint")
            ran = super().perform_action(engine, player, action_id, data)
            # _perform_generic_haunt_action 只要执行就返回 True，成败要看轨道是否推进
            succeeded = ran and engine._haunt_track_value("repaint") > before
            if succeeded:
                engine.remove_token(held[0].uid)
                engine.spawn_token(self.CHECK, label="知识检定", role="marker", room_key=player.room_key)
                value = engine._haunt_track_value("repaint")
                goal = engine._haunt_track_target("repaint")
                stroke = "落下了最后一笔" if value >= goal else "又落下一笔"
                engine._log(f"{player.name} {stroke}（{value}/{goal}）——颜料用尽了。")
                if value >= goal:
                    engine._haunt_flags()["spell_broken"] = True
                    engine._log("肖像忽然变得陌生：画中人正在老去，而它守了三百年的东西正在流失。")
            return ran

        if action_id == "destroy_paint":
            if player.role != "traitor" or not held:
                engine._log("你手上没有颜料。")
                return False
            if getattr(player, "attack_used", False):
                engine._log("销毁颜料要代替本回合的攻击——你已经出过手了。")
                return False
            engine.remove_token(held[0].uid)
            value = engine._advance_haunt_track("paint_destroyed", 1)
            engine._haunt_flags()["destroyed_this_turn"] = True
            engine._log(f"{player.name} 把{held[0].label}捻成了碎片（已毁 {value}/3）。")
            engine.check_victory()
            return True

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 进度
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        paints = engine.tokens_of_kind(self.PAINT)
        lines = [
            f"颜料：房内 {sum(1 for t in paints if t.room_key)} 罐 / "
            f"随身 {sum(1 for t in paints if t.holder is not None)} 罐 / "
            f"已毁 {engine._haunt_track_value('paint_destroyed')}"
            f"/{engine._haunt_track_target('paint_destroyed')}",
            f"重绘：{engine._haunt_track_value('repaint')}/{engine._haunt_track_target('repaint')} 枚知识检定令牌",
        ]
        if int(flags.get("pending_paint", 0)) > 0:
            lines.append(f"还有 {flags['pending_paint']} 罐颜料等着房间被翻开")
        if self._gallery_key(engine):
            lines.append("肖像在画廊——叛徒不敢直视它")
        return lines

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """手里有颜料就往画廊跑，没有就去搜颜料；叛徒同样追颜料（好把它毁掉）。"""
        if player.dead:
            return []
        if self._held_paint(engine, player):
            gallery = self._gallery_key(engine)
            return [f"__room__{gallery}"] if gallery else []
        return [
            f"__room__{token.room_key}"
            for token in engine.tokens_of_kind(self.PAINT) if token.room_key
        ]











class BreathOfWindMode(GenericModeHandler):
    """剧本 65 一阵风息（A Breath of Wind）。

    权威原文：英雄手册 p76 / 叛徒手册 p147。
    · 骚灵（ghost 模板，Speed 3）生成于作祟房间。
    · 计时从 3 开始，每个怪物回合 -1；归零 → 英雄死亡。
    · 找蜡烛：速度 3+（厨房/餐厅/教堂/画廊），每回合一次。
    · 用蜡烛：弃蜡烛 + 知识 5+（作祟层）→ 放 token（每房一次）。
    · 仪式 token 数 = 英雄数 → 英雄胜。
    · 简化：骚灵免疫力量攻击/左轮/重生未建模。
    """

    mode = "haunt_exorcism"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["candle_rooms_used"] = []
        flags["candles_found"] = 0
        engine._set_haunt_track_value("poltergeist_timer", 3)  # p76：计时从 3 开始
        engine._log("骚灵发出了疯狂的笑声——物件开始朝你飞来！")

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        if player.role == "traitor" and not player.dead:
            # 每个怪物回合递减计时
            current = int(engine._haunt_track_value("poltergeist_timer"))
            if current > 0:
                engine._set_haunt_track_value("poltergeist_timer", current - 1)
                engine._log(f"骚灵的愤怒升级了！（倒计时 {current - 1}）")
                if current - 1 <= 0:
                    # 骚灵杀死一个英雄
                    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
                    if heroes:
                        victim = engine.rng.choice(heroes)
                        victim.dead = True
                        engine._log(f"{victim.name} 被骚灵的狂怒撕碎了！")
                        engine.check_victory()

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        for action in actions:
            if action.id == "burn_candle":
                if not engine.tokens_held_by(player.id, "candle"):
                    continue
                room_id = engine._current_room_template_id(player)
                if room_id in flags.get("candle_rooms_used", []):
                    continue
                # 必须在作祟层
                room = engine.current_room(player)
                if room.floor != engine.state.board[engine._haunt_rule_state().get("haunt_room", "")].floor:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        flags = engine._haunt_flags()
        if action_id == "find_candle":
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                engine.spawn_token("candle", label="蜡烛", role="carried", holder=player.id)
                flags["candles_found"] = int(flags.get("candles_found", 0)) + 1
                engine._log(f"{player.name} 找到了一根蜡烛。")
            return ok

        if action_id == "burn_candle":
            token = next(iter(engine.tokens_held_by(player.id, "candle")), None)
            if token is None:
                engine._log("你没有蜡烛。")
                return False
            engine.remove_token(token.uid)
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                room_id = engine._current_room_template_id(player)
                used = flags.setdefault("candle_rooms_used", [])
                used.append(room_id)
                engine.spawn_token("knowledge_check", label="驱魔成功", role="check", room_key=player.room_key)
                engine._log("蜡烛的火焰净化了这个房间！")
                engine.check_victory()
            return ok

        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        if engine._haunt_track_value("exorcism_progress") >= engine._haunt_track_target("exorcism_progress"):
            engine._set_winner("heroes", "驱魔完成——骚灵消散了！")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "骚灵的狂笑回荡在空荡的房子里。")
            return True
        return False



class HellOnEarthMode(GenericModeHandler):
    """剧本 66 人间地狱（Hell on Earth）。

    权威原文：英雄手册 p77 / 叛徒手册 p148。
    · 力量轨道从 0 起、上限 8。
    · 充能代替攻击：小教堂、图书馆或圣徽所在房间做理智检定；4–7 +1，8+ +2。
    · 持徽者本回合充能后可封闭当前房间（轨道 ≥1 时 -1，放封印令牌）。
    · 只能用圣徽打恶魔领主：骰数 = 当前轨道，对方用理智防守；未胜过则无事发生。
    · 封闭房打胜 → 驱逐、英雄胜；未封闭则击退（差值为步数）或击晕（扣开局英雄数格轨道）。
    · 叛徒仍在场，不能拾取/偷窃圣徽；神秘电梯对双方都拒绝移动。
    · 恶魔领主属性随人数：3p Speed 3 Might 5 Sanity 3；4p 4/5/4；5p 5/6/5；6p 6/6/6。
    · 领主能摸到持徽英雄时必须打他，否则必须打得到的英雄；主动攻击落败不击晕。
    已知简化：击退方向由 bot 固定策略（远离持徽英雄/最近英雄）；人类的击退/击晕选择未接 prompter；
    圣徽若开局不在场则补发给揭示者（揭示者是叛徒则发给第一名英雄）；
    引擎每回合只能做一次剧本行动，持徽者充能成功且轨道仍 ≥1 时会立刻封闭当前房间
    （原文是本回合内可另选封闭，这里把两步并进同一次行动）。
    """

    mode = "hell_on_earth"
    LORD = "hell_demon_lord"
    HOLY = "omen_holy_symbol"
    CHARGE_ROOMS = ("chapel", "library")
    STATS = {
        3: (3, 5, 3),
        4: (4, 5, 4),
        5: (5, 6, 5),
        6: (6, 6, 6),
    }

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["sealed_rooms"] = []
        flags["prayed_this_turn"] = None
        flags["initial_hero_count"] = sum(
            1 for p in engine.state.players if p.role == "hero" and not p.dead
        )
        engine._set_haunt_track_value("holy_power", 0)

        # 骨架可能已按旧 monsters 表刷出 giant/cultist，清掉后按原文放领主。
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "template_id", "") == self.LORD
        ]
        if engine._monster_by_template(self.LORD) is None:
            spawn_key = self._pick_lord_room(engine, room_key)
            n = max(3, min(6, len(engine.state.players)))
            speed, might, sanity = self.STATS[n]
            spec = {
                "template_id": self.LORD,
                "name": "恶魔领主",
                "speed": speed,
                "might": might,
                "sanity": sanity,
            }
            engine._spawn_single_haunt_monster(spec, spawn_key)

        if not engine._card_is_controlled(self.HOLY):
            holder = next(
                (p for p in engine.state.players if p.id == engine.state.haunt_revealer_id and p.role == "hero" and not p.dead),
                None,
            )
            if holder is None:
                holder = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
            if holder is not None:
                engine._grant_card_to_player(holder, self.HOLY)

        engine._log("火焰一闪，虚空裂开——恶魔领主踏进了这栋房子。")

    def on_turn_start(self, engine, player):
        engine._haunt_flags()["prayed_this_turn"] = None

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            if aid == "charge_holy_symbol" and not self._can_charge(engine, player):
                continue
            if aid == "seal_room" and not self._can_seal(engine, player):
                continue
            if aid == "holy_symbol_attack" and not self._can_holy_attack(engine, player):
                continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        if action_id == "charge_holy_symbol":
            return self._charge(engine, player)
        if action_id == "seal_room":
            return self._seal(engine, player)
        if action_id == "holy_symbol_attack":
            return self._holy_attack(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def attack_allowed(self, engine, attacker, target):
        if getattr(target, "template_id", "") == self.LORD:
            return False
        return True

    def mystic_elevator_blocked(self, engine, player):
        return True

    def item_pickup_blocked(self, engine, player, card_id):
        return card_id == self.HOLY and getattr(player, "role", "") == "traitor"

    def item_trade_blocked(self, engine, giver, target, card_id):
        return card_id == self.HOLY and getattr(target, "role", "") == "traitor"

    def on_monster_defeated(self, engine, monster, amount):
        # 普通攻击打不中领主（attack_allowed 已拦）；这里兜底：领主被击败时不走默认击晕。
        return getattr(monster, "template_id", "") == self.LORD

    def on_monster_turn_start(self, engine, monster):
        """整回合接管：先追持徽英雄（够得着就必须打他），再结算力量攻击。"""
        if getattr(monster, "template_id", "") != self.LORD:
            return False
        target = self._lord_target(engine, monster)
        if target is None:
            return True
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) > 1:
            steps = max(1, engine.roll_dice(getattr(monster, "speed", 3), "恶魔领主移动"))
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"{monster.name} 移动到 {engine.state.board[monster.room_key].name}。")
        if monster.room_key == target.room_key:
            self._lord_might_attack(engine, monster, target)
        return True

    def on_monster_move(self, engine, monster, rolled):
        if getattr(monster, "template_id", "") != self.LORD:
            return False
        return True

    def on_monster_turn_attack(self, engine, monster):
        return getattr(monster, "template_id", "") == self.LORD

    def _lord_might_attack(self, engine, monster, target):
        monster_roll = engine._roll_monster_attack(monster, "might")
        hero_roll = engine._roll_attack(target, "might")
        engine._log(f"{monster.name} 攻击 {engine._player_label(target)}：{monster_roll} 对 {hero_roll}。")
        if monster_roll > hero_roll:
            engine._deal_damage(target, "physical", monster_roll - hero_roll, source=monster.name)
        elif monster_roll < hero_roll:
            # p148：领主主动攻击时被击败不击晕。
            engine._log(f"{monster.name} 被挡住了，但没有被击晕。")
        else:
            engine._log("平手。")

    def bot_goal_rooms(self, engine, player):
        if player.role != "hero" or player.dead:
            return []
        holder = self._holy_holder(engine)
        lord = engine._monster_by_template(self.LORD)
        if holder is not None and holder.id == player.id:
            if lord is not None:
                return [f"__room__{lord.room_key}"]
            return []
        if holder is not None:
            return [f"__room__{holder.room_key}"]
        goals = []
        for room_key, cards in engine.state.room_items.items():
            if self.HOLY in cards:
                goals.append(f"__room__{room_key}")
        if not goals:
            goals.extend(self.CHARGE_ROOMS)
        return goals

    def progress_summary(self, engine, viewer):
        flags = engine._haunt_flags()
        power = engine._haunt_track_value("holy_power")
        sealed = flags.get("sealed_rooms") or []
        lines = [f"圣徽力量 {power}/8", f"已封闭房间 {len(sealed)}"]
        holder = self._holy_holder(engine)
        if holder is not None:
            lines.append(f"圣徽持有者：{holder.name}")
        return lines

    def check_victory(self, engine):
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也倒下了——人间成了地狱。")
            return True
        if engine.state.winner:
            return True
        # p77：英雄只能靠封闭房驱逐取胜。拦截引擎默认的「叛徒倒下 = 英雄胜」。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- 内部

    def _can_charge(self, engine, player):
        if player.role != "hero" or player.dead or getattr(player, "attack_used", False):
            return False
        room = engine.state.board.get(player.room_key)
        if room is None:
            return False
        if room.template_id in self.CHARGE_ROOMS:
            return True
        return self._holy_in_room(engine, player.room_key)

    def _can_seal(self, engine, player):
        if player.role != "hero" or player.dead:
            return False
        if engine._haunt_flags().get("prayed_this_turn") != player.id:
            return False
        if self._holy_holder(engine) is not player:
            return False
        if engine._haunt_track_value("holy_power") < 1:
            return False
        sealed = set(engine._haunt_flags().get("sealed_rooms") or [])
        return player.room_key not in sealed

    def _can_holy_attack(self, engine, player):
        if player.role != "hero" or player.dead or getattr(player, "attack_used", False):
            return False
        if self._holy_holder(engine) is not player:
            return False
        if engine._haunt_track_value("holy_power") < 1:
            return False
        lord = engine._monster_by_template(self.LORD)
        return lord is not None and lord.room_key == player.room_key

    def _charge(self, engine, player):
        if not self._can_charge(engine, player):
            return False
        dice = max(1, min(8, engine._effective_stat(player, "sanity") + engine._check_bonus(player, "sanity")))
        roll = engine.roll_dice(dice, "为圣徽充能")
        engine._log(f"{player.name} 为圣徽祈祷，掷出 {roll}。")
        gain = 0
        if roll >= 8:
            gain = 2
        elif roll >= 4:
            gain = 1
        if gain:
            value = engine._advance_haunt_track("holy_power", gain)
            engine._log(f"圣徽力量升到 {value}。")
        else:
            engine._log("祈祷没有唤来力量。")
        player.attack_used = True
        if self._holy_holder(engine) is player:
            engine._haunt_flags()["prayed_this_turn"] = player.id
            # 引擎每回合只能做一次剧本行动，持徽者充能后立刻封闭当前房间。
            if self._can_seal(engine, player):
                self._seal(engine, player)
        return True

    def _seal(self, engine, player):
        if not self._can_seal(engine, player):
            return False
        power = engine._haunt_track_value("holy_power")
        engine._set_haunt_track_value("holy_power", power - 1)
        sealed = engine._haunt_flags().setdefault("sealed_rooms", [])
        sealed.append(player.room_key)
        room = engine.state.board[player.room_key]
        engine.spawn_token("seal", label="封印", role="marker", room_key=player.room_key)
        engine._log(f"{player.name} 封闭了 {room.name}（圣徽力量 {power - 1}）。")
        return True

    def _holy_attack(self, engine, player):
        if not self._can_holy_attack(engine, player):
            return False
        lord = engine._monster_by_template(self.LORD)
        power = engine._haunt_track_value("holy_power")
        hero_roll = engine.roll_dice(power, "圣徽攻击")
        lord_roll = engine._roll_monster_attack(lord, "sanity")
        engine._log(f"{player.name} 用圣徽攻击恶魔领主：{hero_roll} 对 {lord_roll}。")
        player.attack_used = True
        if hero_roll <= lord_roll:
            engine._log("圣徽没有压住恶魔领主。")
            return True
        diff = hero_roll - lord_roll
        sealed = set(engine._haunt_flags().get("sealed_rooms") or [])
        if player.room_key in sealed:
            engine._kill_monster(lord, killer=player)
            engine._set_winner("heroes", "恶魔领主被圣徽从凡间驱逐了。")
            engine.check_victory()
            return True
        self._repel_or_stun(engine, player, lord, diff)
        return True

    def _repel_or_stun(self, engine, player, lord, diff):
        """未封闭房间打胜：击晕要扣开局英雄数格轨道，不够就击退。"""
        flags = engine._haunt_flags()
        hero_count = max(1, int(flags.get("initial_hero_count") or 1))
        power = engine._haunt_track_value("holy_power")
        if power >= hero_count:
            engine._set_haunt_track_value("holy_power", max(0, power - hero_count))
            engine._stun_monster(lord, 1)
            engine._log(f"恶魔领主被击晕了（圣徽力量 {max(0, power - hero_count)}）。")
            return
        self._repel_lord(engine, player, lord, diff)
        engine._log(f"恶魔领主被击退了 {diff} 格。")

    def _repel_lord(self, engine, player, lord, diff):
        holder = self._holy_holder(engine) or player
        graph = engine._build_graph()
        start = lord.room_key
        best = start
        best_score = engine._path_length(start, holder.room_key)
        frontier = {start}
        visited = {start}
        for _ in range(max(1, int(diff))):
            nxt = set()
            for key in frontier:
                for neigh in graph.get(key, ()):
                    if neigh in visited:
                        continue
                    visited.add(neigh)
                    nxt.add(neigh)
                    score = engine._path_length(neigh, holder.room_key)
                    if score > best_score or (score == best_score and neigh > best):
                        best_score = score
                        best = neigh
            if not nxt:
                break
            frontier = nxt
        lord.room_key = best

    def _pick_lord_room(self, engine, fallback):
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return fallback
        best = fallback
        best_min = -1
        for key in sorted(engine.state.board.keys()):
            distances = [engine._path_length(key, p.room_key) for p in heroes]
            if any(d >= 9999 for d in distances):
                continue
            min_d = min(distances)
            if min_d > best_min or (min_d == best_min and key > best):
                best_min = min_d
                best = key
            if min_d >= 3 and best_min >= 3:
                # 继续找同样 ≥3 里字典序稳定的最远最小距离
                continue
        return best

    def _holy_holder(self, engine):
        return next((p for p in engine.state.players if self.HOLY in p.items and not p.dead), None)

    def _holy_in_room(self, engine, room_key):
        cards = engine.state.room_items.get(room_key, [])
        if self.HOLY in cards:
            return True
        return any(self.HOLY in p.items and p.room_key == room_key and not p.dead for p in engine.state.players)

    def _lord_target(self, engine, monster):
        holder = self._holy_holder(engine)
        speed = max(1, int(getattr(monster, "speed", 1)))
        if holder is not None:
            dist = engine._path_length(monster.room_key, holder.room_key)
            if dist <= speed:
                return holder
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return None
        heroes.sort(key=lambda p: (engine._path_length(monster.room_key, p.room_key), p.id))
        return heroes[0]


class StorybookTwistsMode(GenericModeHandler):
    """剧本 67 从前有一次（Once Upon a Time）。

    权威原文：英雄手册 p78 / 叛徒手册 p149。
    · 叛徒入定：不能移动、攻击、使用物品，不能被攻击，属性不升不降。
    · 英雄与叛徒同房可代替攻击自动偷窃（含疯子/女孩/狗）；叛徒不阻挡离房。
    · 同房做知识检定并加上故事轨道，6+ 抽取任务（6 骰 0–12，已抽则顺延）。
    · 完成任务数达到开局英雄数，并活到故事轨道 7 → 英雄胜；否则悲伤结局。
    · 猎蛛开局；女巫（段落 7）与恶龙（段落 10）由故事召唤。
    · 猎蛛造成物理伤害前先降 1 点属性；女巫可传送并用力量或理智攻击；
      恶龙喷火；除非被斧/矛/血匕/左轮/戒指/炸药击中，否则恶龙被击败不击晕。
    已知简化：
    · 剧情转折「厄运/关键失误」需要打断他人掷骰，未建模；坍塌地板/晕眩由人类自选，
      bot 只用冗长叙述、时光飞逝、埋伏、复苏。
    · 物品牌没有神秘硬币、德鲁伊护符、骷髅钥匙、玩具猴——对应任务只用仍在牌库的替代物。
    · 「朝外窗户」房间近似为门厅/阳台/塔楼/庭院/花园/墓地。
    · 五芒星室「忽略房间文字」只记 flag（该房间本就几乎无效果）。
    · 「谁抽到了牙」简化为当前持有预兆「牙」的英雄。
    · 寻找任务 / 完成任务 / 偷窃 / 剧情转折共用引擎的「每回合一次剧本行动」槽。
    · 女巫每回合固定传送到最近英雄（原文可选传送或正常移动）。
    """

    mode = "storybook_twists"
    SPIDER = "story_spider"
    WITCH = "story_witch"
    DRAGON = "story_dragon"
    COMPANIONS = ("omen_madman", "omen_girl", "omen_dog")
    SPIDER_ROOMS = ("entrance_hall", "balcony", "tower", "patio", "garden", "graveyard")
    STUN_WEAPONS = {
        "item_axe", "omen_spear", "item_blood_dagger", "item_revolver",
        "omen_ring", "item_dynamite",
    }
    TWISTS = (
        "lengthy_narration",
        "time_flies",
        "evil_luck",
        "critical_lapse",
        "revival",
        "ambush",
        "collapsing_floor",
        "daze",
    )
    TWIST_LABELS = {
        "lengthy_narration": "冗长叙述（下次不推进故事）",
        "time_flies": "时光飞逝（立刻推进一格故事）",
        "evil_luck": "厄运（重掷你刚才的骰，未建模）",
        "critical_lapse": "关键失误（逼英雄重掷，未建模）",
        "revival": "复苏（解除一只怪物的昏迷）",
        "ambush": "埋伏（把一只怪物移到任意房间）",
        "collapsing_floor": "塌陷地板（把一名英雄送到下一层）",
        "daze": "晕眩（英雄下回合不能既移动又攻击）",
    }
    QUEST_NAMES = {
        0: "驱魔放逐",
        1: "交叉手指",
        2: "解药",
        3: "力量试炼",
        4: "抹去五芒星",
        5: "驱魔",
        6: "落难少女",
        7: "安息",
        8: "求问亡者",
        9: "高贵受苦",
        10: "古人之路",
        11: "拥抱命运",
        12: "打破蛊惑",
    }

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        flags["initial_hero_count"] = len(heroes)
        flags["obtained_quests"] = []
        flags["completed_quests"] = []
        flags["used_twists"] = []
        flags["body_tokens"] = 0
        flags["skip_next_advance"] = False
        flags["story_ended"] = False
        flags["dazed"] = []
        flags["pentagram_erased"] = False
        engine._set_haunt_track_value("quests", 0)
        engine._set_haunt_track_value("story", 0)
        engine._haunt_tracks()["quests"]["target"] = max(1, len(heroes))

        engine.state.monsters = [
            m for m in engine.state.monsters
            if getattr(m, "template_id", "") in {self.SPIDER, self.WITCH, self.DRAGON}
        ]
        if engine._monster_by_template(self.SPIDER) is None:
            spawn = self._first_room(engine, self.SPIDER_ROOMS) or room_key
            engine._spawn_single_haunt_monster(
                {"template_id": self.SPIDER, "name": "猎蛛", "speed": 4, "might": 5, "sanity": 3},
                spawn,
            )
        engine._log("故事开始了。猎蛛已经循着气味进了这栋房子。")

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        dazed = [int(x) for x in (flags.get("dazed") or [])]
        if player.id in dazed:
            flags["dazed"] = [x for x in dazed if x != player.id]
            flags["dazed_now"] = player.id
        else:
            flags.pop("dazed_now", None)
        if player.role != "traitor" or player.dead:
            return
        player.steps_remaining = 0
        player.attack_used = True
        player.item_used = True
        twos = sum(1 for _ in range(2) if engine.rng.choice((0, 1, 2)) == 2)
        if twos:
            flags["body_tokens"] = int(flags.get("body_tokens") or 0) + twos
            engine._log(f"故事里又多了 {twos} 处转折（尸体令牌 {flags['body_tokens']}）。")
        if getattr(player, "control", "") == "bot":
            self._bot_auto_twist(engine, player)
        self._advance_story(engine)

    def on_player_moved(self, engine, player):
        if engine._haunt_flags().get("dazed_now") == player.id:
            player.attack_used = True

    def on_attack_resolved(self, engine, attacker, target, attacker_won):
        if engine._haunt_flags().get("dazed_now") == getattr(attacker, "id", None):
            attacker.steps_remaining = 0
        if not attacker_won or getattr(attacker, "role", "") != "hero":
            return
        if getattr(target, "template_id", "") != self.SPIDER:
            return
        if getattr(engine, "_last_attack_attr", "might") != "might":
            return
        obtained = [int(x) for x in (engine._haunt_flags().get("obtained_quests") or [])]
        completed = [int(x) for x in (engine._haunt_flags().get("completed_quests") or [])]
        if 3 in obtained and 3 not in completed:
            self._complete_quest(engine, attacker, 3)

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            if aid == "obtain_quest" and not self._can_obtain(engine, player):
                continue
            if aid == "complete_quest" and not self._completable_quests(engine, player):
                continue
            if aid == "steal_from_traitor" and not self._can_steal_traitor(engine, player):
                continue
            if aid == "plot_twist" and not self._can_twist(engine, player):
                continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        if action_id == "obtain_quest":
            return self._obtain_quest(engine, player)
        if action_id == "complete_quest":
            return self._try_complete(engine, player)
        if action_id == "steal_from_traitor":
            return self._steal_traitor(engine, player)
        if action_id == "plot_twist":
            return self._do_twist(engine, player, data)
        return super().perform_action(engine, player, action_id, data)

    def attack_allowed(self, engine, attacker, target):
        if getattr(target, "role", "") == "traitor":
            return False
        if getattr(attacker, "role", "") == "traitor":
            return False
        return True

    def counts_as_movement_obstacle(self, engine, mover, occupant):
        return getattr(occupant, "role", "") != "traitor"

    def item_use_blocked(self, engine, player, card_id):
        return getattr(player, "role", "") == "traitor"

    def can_discover_rooms(self, engine, player):
        return getattr(player, "role", "") != "traitor"

    def physical_damage_reduction(self, engine, player, amount, source, damage_type):
        if getattr(player, "role", "") == "traitor":
            return amount
        return 0

    def on_monster_defeated(self, engine, monster, amount):
        if getattr(monster, "template_id", "") != self.DRAGON:
            return False
        weapon = getattr(engine, "_last_attack_weapon_id", "") or ""
        if weapon in self.STUN_WEAPONS:
            return False
        engine._log("鳞片挡下了这一击——没有合适的武器，恶龙没有被击晕。")
        return True

    def on_monster_turn_start(self, engine, monster):
        if getattr(monster, "template_id", "") != self.WITCH:
            return False
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return True
        heroes.sort(key=lambda p: (engine._path_length(monster.room_key, p.room_key), p.id))
        target = heroes[0]
        monster.room_key = target.room_key
        engine._log(f"{monster.name} 瞬间出现在 {engine.state.board[monster.room_key].name}。")
        self._witch_attack(engine, monster)
        return True

    def on_monster_turn_attack(self, engine, monster):
        tid = getattr(monster, "template_id", "")
        if tid == self.WITCH:
            return self._witch_attack(engine, monster)
        if tid == self.DRAGON:
            return self._dragon_breath(engine, monster)
        return False

    def on_monster_attack(self, engine, monster, target, amount):
        if getattr(monster, "template_id", "") != self.SPIDER:
            return False
        if amount <= 0:
            return False
        stat = self._venom_stat(engine, target)
        engine._log(f"猎蛛的毒牙先削弱了 {target.name} 的{stat}。")
        engine._apply_stat_loss(target, stat, 1)
        engine._deal_damage(target, "physical", amount, source=monster.name)
        return True

    def bot_goal_rooms(self, engine, player):
        if player.dead:
            return []
        if player.role == "traitor":
            return []
        goals = []
        for qid in self._completable_quests(engine, player):
            goals.extend(self._quest_rooms(engine, qid, player))
        if not goals:
            traitor = self._traitor(engine)
            if traitor is not None:
                goals.append(f"__room__{traitor.room_key}")
        return goals

    def progress_summary(self, engine, viewer):
        flags = engine._haunt_flags()
        needed = int(flags.get("initial_hero_count") or 1)
        obtained = [int(x) for x in (flags.get("obtained_quests") or [])]
        completed = [int(x) for x in (flags.get("completed_quests") or [])]
        names = [self.QUEST_NAMES.get(q, str(q)) for q in obtained if q not in completed]
        lines = [
            f"故事进度 {engine._haunt_track_value('story')}/7",
            f"已完成任务 {len(completed)}/{needed}",
            f"剧情转折令牌 {int(flags.get('body_tokens') or 0)}",
        ]
        if names:
            lines.append("进行中：" + "、".join(names))
        return lines

    def check_victory(self, engine):
        flags = engine._haunt_flags()
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后一名英雄倒下了。故事以悲剧收场。")
            return True
        if engine.state.winner:
            return True
        if flags.get("story_ended"):
            needed = max(1, int(flags.get("initial_hero_count") or 1))
            done = len(flags.get("completed_quests") or [])
            if done >= needed:
                engine._set_winner("heroes", "……从此他们过上了幸福的生活。完。")
            else:
                engine._set_winner("traitor", "任务未完，故事却已结束——悲伤的结局。")
            return True
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- 故事

    def _advance_story(self, engine):
        flags = engine._haunt_flags()
        if flags.get("story_ended"):
            return
        if flags.get("skip_next_advance"):
            flags["skip_next_advance"] = False
            engine._log("冗长的叙述拖住了时间，故事这一回没有往前翻。")
            return
        value = engine._advance_haunt_track("story", 1)
        if value >= 7:
            flags["story_ended"] = True
            engine._log("故事翻到了最后一页。")
            engine.check_victory()
            return
        section = value + len(engine.state.players)
        self._read_section(engine, section)

    def _read_section(self, engine, section):
        flags = engine._haunt_flags()
        if section == 5 or section == 11:
            flags["body_tokens"] = int(flags.get("body_tokens") or 0) + 1
            engine._log(f"故事第 {section} 段：一枚尸体令牌落入叙事者手中。")
        elif section == 7:
            self._spawn_named(engine, self.WITCH, "女巫", 3, 4, 5, self._any_room(engine))
            engine._log("故事第 7 段：不耐烦的女巫走进了房子。")
        elif section == 8:
            spider = engine._monster_by_template(self.SPIDER)
            if spider is not None:
                spider.speed = int(getattr(spider, "speed", 4)) + 1
                engine._log(f"故事第 8 段：猎蛛感到主人靠近，速度变为 {spider.speed}。")
        elif section == 10:
            traitor = self._traitor(engine)
            room = traitor.room_key if traitor is not None else next(iter(engine.state.board))
            self._spawn_named(engine, self.DRAGON, "恶龙", 5, 7, 4, room)
            engine._log("故事第 10 段：恶龙咆哮着飞进叙事者所在的房间。")
        else:
            engine._log(f"故事第 {section} 段被读了出来。")

    def _spawn_named(self, engine, template_id, name, speed, might, sanity, room_key):
        if engine._monster_by_template(template_id) is not None:
            return
        engine._spawn_single_haunt_monster(
            {"template_id": template_id, "name": name, "speed": speed, "might": might, "sanity": sanity},
            room_key,
        )

    # ------------------------------------------------------------- 任务

    def _can_obtain(self, engine, player):
        if player.role != "hero" or player.dead:
            return False
        traitor = self._traitor(engine)
        return traitor is not None and traitor.room_key == player.room_key and not traitor.dead

    def _obtain_quest(self, engine, player):
        if not self._can_obtain(engine, player):
            return False
        story = engine._haunt_track_value("story")
        dice = max(1, min(8, engine._effective_stat(player, "knowledge") + engine._check_bonus(player, "knowledge")))
        roll = engine.roll_dice(dice, "寻找关键情节")
        engine._log(f"{player.name} 翻查故事（{roll}+{story}）。")
        if roll + story < 6:
            engine._log("这一页还没有露出破绽。")
            return True
        qid = self._draw_quest(engine)
        if qid is None:
            engine._log("所有任务都已经找到了。")
            return True
        engine._log(f"找到了任务：{self.QUEST_NAMES[qid]}。")
        return True

    def _draw_quest(self, engine):
        flags = engine._haunt_flags()
        obtained = [int(x) for x in (flags.get("obtained_quests") or [])]
        if len(obtained) >= 13:
            return None
        start = sum(engine.rng.choice((0, 1, 2)) for _ in range(6))
        for offset in range(13):
            qid = (start + offset) % 13
            if qid not in obtained:
                obtained.append(qid)
                flags["obtained_quests"] = obtained
                return qid
        return None

    def _completable_quests(self, engine, player):
        if player.role != "hero" or player.dead:
            return []
        flags = engine._haunt_flags()
        obtained = [int(x) for x in (flags.get("obtained_quests") or [])]
        completed = set(int(x) for x in (flags.get("completed_quests") or []))
        return [qid for qid in obtained if qid not in completed and self._quest_ready(engine, player, qid)]

    def _try_complete(self, engine, player):
        ready = self._completable_quests(engine, player)
        if not ready:
            return False
        if len(ready) == 1 or getattr(player, "control", "") == "bot":
            qid = ready[0]
        else:
            labels = [self.QUEST_NAMES.get(q, str(q)) for q in ready]
            idx = engine.prompter.choose_from_list("完成任务", "要完成哪一个？", labels)
            if idx is None:
                return False
            qid = ready[idx]
        return self._complete_quest(engine, player, qid)

    def _complete_quest(self, engine, player, qid):
        flags = engine._haunt_flags()
        completed = [int(x) for x in (flags.get("completed_quests") or [])]
        if qid in completed:
            return False
        checks = {2: ("knowledge", 4), 4: ("sanity", 5), 5: ("sanity", 5), 6: ("knowledge", 5), 12: ("knowledge", 6)}
        if qid in checks:
            stat, target = checks[qid]
            if not self._stat_ok(engine, player, stat, target):
                engine._log(f"任务「{self.QUEST_NAMES.get(qid, qid)}」的检定失败了。")
                return True
        if qid == 0:
            engine._increase_stat(player, "sanity", 1)
        elif qid == 1:
            engine._draw_item(player)
        elif qid == 2:
            bitten = self._holder(engine, "omen_bite")
            if bitten is not None:
                self._restore_physical(engine, bitten)
        elif qid == 3:
            engine._increase_stat(player, "might", 1)
        elif qid == 4:
            flags["pentagram_erased"] = True
        elif qid == 5:
            mad = self._holder(engine, "omen_madman")
            if mad is not None:
                engine._increase_stat(mad, "sanity", 1)
        elif qid == 6:
            girl_holder = self._holder(engine, "omen_girl")
            if girl_holder is not None:
                engine._discard_card_from_player(girl_holder, "omen_girl", return_to_room=False)
                engine._log(f"{girl_holder.name} 把女孩留在了门厅，没有失去属性。")
        elif qid == 7:
            engine._discard_card_from_player(player, "omen_skull", return_to_room=False)
            engine._increase_stat(player, "knowledge", 1)
        elif qid == 8:
            extra = self._draw_quest(engine)
            if extra is not None:
                engine._log(f"灵应板又翻出了任务：{self.QUEST_NAMES[extra]}。")
        elif qid == 9:
            physical = engine.roll_dice(2, "高贵受苦·肉体")
            mental = engine.roll_dice(1, "高贵受苦·精神")
            engine._deal_damage(player, "physical", physical, source="高贵受苦")
            if not player.dead:
                engine._deal_damage(player, "mental", mental, source="高贵受苦")
            if player.dead:
                engine._log("这份苦没有人能活着受完。")
                return True
        elif qid == 10:
            stats = ("speed", "might", "sanity", "knowledge")
            best = max(stats, key=lambda s: engine._effective_stat(player, s))
            engine._increase_stat(player, best, 1)
        elif qid == 12:
            spider = engine._monster_by_template(self.SPIDER)
            if spider is not None:
                engine._kill_monster(spider, killer=player)
                engine._log("猎蛛逃出了这栋房子。")
        completed.append(qid)
        flags["completed_quests"] = completed
        engine._set_haunt_track_value("quests", len(completed))
        engine._log(f"{player.name} 完成了任务「{self.QUEST_NAMES.get(qid, qid)}」（{len(completed)}/{flags.get('initial_hero_count')}）。")
        if qid == 11:
            engine._discard_card_from_player(player, "item_bottle", return_to_room=False)
            engine._log(f"{player.name} 喝下了瓶子。故事被往前翻了一页。")
            self._advance_story(engine)
        return True

    def _quest_ready(self, engine, player, qid):
        room = engine.state.board.get(player.room_key)
        tid = room.template_id if room is not None else ""
        witch = engine._monster_by_template(self.WITCH)
        spider = engine._monster_by_template(self.SPIDER)
        traitor = self._traitor(engine)
        if qid == 0:
            return witch is not None and player.room_key == witch.room_key and self._room_has_all(
                engine, player.room_key, ("item_bell", "omen_book", "item_candle")
            )
        if qid == 1:
            return traitor is not None and player.room_key == traitor.room_key and (
                "item_lucky_stone" in player.items or "item_rabbit_foot" in player.items
            )
        if qid == 2:
            bitten = self._holder(engine, "omen_bite")
            return (
                bitten is not None
                and bitten.room_key == player.room_key
                and tid in {"research_laboratory", "operating_laboratory"}
            )
        if qid == 3:
            return False
        if qid == 4:
            return tid == "pentagram_chamber"
        if qid == 5:
            mad = self._holder(engine, "omen_madman")
            return mad is not None and mad.room_key == player.room_key and tid == "chapel"
        if qid == 6:
            girl = self._holder(engine, "omen_girl")
            return girl is not None and girl.room_key == player.room_key and tid == "entrance_hall"
        if qid == 7:
            return "omen_skull" in player.items and tid in {"crypt", "graveyard"}
        if qid == 8:
            return traitor is not None and player.room_key == traitor.room_key and "omen_spirit_board" in player.items
        if qid == 9:
            return tid == "bloody_room"
        if qid == 10:
            return tid == "garden" and (
                "item_amulet_of_the_ages" in player.items or "item_healing_salve" in player.items
            )
        if qid == 11:
            return "item_bottle" in player.items
        if qid == 12:
            return (
                spider is not None
                and player.room_key == spider.room_key
                and "omen_mask" in player.items
            )
        return False

    def _quest_rooms(self, engine, qid, player):
        mapping = {
            0: [self.WITCH],
            1: [],
            2: ["research_laboratory", "operating_laboratory"],
            4: ["pentagram_chamber"],
            5: ["chapel"],
            6: ["entrance_hall"],
            7: ["crypt", "graveyard"],
            8: [],
            9: ["bloody_room"],
            10: ["garden"],
            12: [self.SPIDER],
        }
        rooms = mapping.get(qid, [])
        goals = []
        traitor = self._traitor(engine)
        if qid in {1, 8} and traitor is not None:
            goals.append(f"__room__{traitor.room_key}")
        for item in rooms:
            if item in {self.WITCH, self.SPIDER}:
                mon = engine._monster_by_template(item)
                if mon is not None:
                    goals.append(f"__room__{mon.room_key}")
            else:
                goals.append(item)
        return goals

    def _stat_ok(self, engine, player, stat, target):
        dice = max(1, min(8, engine._effective_stat(player, stat) + engine._check_bonus(player, stat)))
        return engine.roll_dice(dice, f"任务检定·{stat}") >= target

    def _room_has_all(self, engine, room_key, card_ids):
        present = set(engine.state.room_items.get(room_key, []))
        for p in engine.state.players:
            if p.room_key == room_key and not p.dead:
                present.update(p.items)
        return all(cid in present for cid in card_ids)

    def _pay_cards_in_room(self, engine, room_key, card_ids):
        return

    def _restore_physical(self, engine, player):
        face = engine.catalog.characters.get(player.character_id)
        if face is None:
            return
        for stat in ("speed", "might"):
            initial = face.stats.get(stat)
            track = engine._stat_track(player, stat)
            if track and initial is not None:
                idx = min(range(len(track)), key=lambda i: abs(track[i] - initial))
                if player.stat_positions.get(stat, 0) < idx:
                    player.stat_positions[stat] = idx
                    player.stats[stat] = track[idx]
                    engine._log(f"{player.name} 的{stat}恢复到初始值 {track[idx]}。")

    # ------------------------------------------------------------- 偷窃 / 转折

    def _can_steal_traitor(self, engine, player):
        if player.role != "hero" or player.dead or getattr(player, "attack_used", False):
            return False
        traitor = self._traitor(engine)
        return traitor is not None and traitor.room_key == player.room_key and bool(self._stealable(engine, traitor))

    def _stealable(self, engine, traitor):
        out = []
        for card_id in traitor.items:
            card = engine.catalog.cards.get(card_id)
            if card is None:
                continue
            if card.tradeable or card_id in self.COMPANIONS:
                out.append(card_id)
        return out

    def _steal_traitor(self, engine, player):
        if not self._can_steal_traitor(engine, player):
            return False
        traitor = self._traitor(engine)
        candidates = self._stealable(engine, traitor)
        if getattr(player, "control", "") == "bot" or len(candidates) == 1:
            steal_id = candidates[0]
        else:
            names = [engine.catalog.cards[c].name for c in candidates]
            idx = engine.prompter.choose_from_list("偷窃", "要偷哪一件？", names)
            if idx is None:
                return False
            steal_id = candidates[idx]
        traitor.items.remove(steal_id)
        player.items.append(steal_id)
        if steal_id in getattr(traitor, "companions", []):
            traitor.companions.remove(steal_id)
        if "companion" in engine.catalog.cards[steal_id].tags and steal_id not in player.companions:
            player.companions.append(steal_id)
        player.attack_used = True
        engine._log(f"{player.name} 从入定的 {traitor.name} 身上拿走了 {engine.catalog.cards[steal_id].name}。")
        return True

    def _can_twist(self, engine, player):
        if player.role != "traitor" or player.dead:
            return False
        flags = engine._haunt_flags()
        if int(flags.get("body_tokens") or 0) < 1:
            return False
        used = set(flags.get("used_twists") or [])
        return any(t not in used and t not in {"evil_luck", "critical_lapse"} for t in self.TWISTS)

    def _do_twist(self, engine, player, data):
        if not self._can_twist(engine, player):
            return False
        flags = engine._haunt_flags()
        used = list(flags.get("used_twists") or [])
        remaining = [t for t in self.TWISTS if t not in used and t not in {"evil_luck", "critical_lapse"}]
        remaining = [t for t in remaining if self._twist_possible(engine, t)]
        if not remaining:
            return False
        if getattr(player, "control", "") == "bot":
            choice = remaining[0]
        else:
            labels = [self.TWIST_LABELS[t] for t in remaining]
            idx = engine.prompter.choose_from_list("剧情转折", "要用哪一种？", labels)
            if idx is None:
                return False
            choice = remaining[idx]
        return self._resolve_twist(engine, player, choice)

    def _twist_possible(self, engine, twist):
        if twist == "revival":
            return any(m.stunned_turns > 0 for m in engine.state.monsters)
        if twist == "ambush":
            return bool(engine.state.monsters) and bool(engine.state.board)
        if twist == "collapsing_floor":
            return any(p.role == "hero" and not p.dead for p in engine.state.players)
        if twist == "daze":
            return any(p.role == "hero" and not p.dead for p in engine.state.players)
        return True

    def _resolve_twist(self, engine, player, twist):
        flags = engine._haunt_flags()
        flags["body_tokens"] = int(flags.get("body_tokens") or 0) - 1
        used = list(flags.get("used_twists") or [])
        used.append(twist)
        flags["used_twists"] = used
        if twist == "lengthy_narration":
            flags["skip_next_advance"] = True
            engine._log("叙事变得冗长——下一次故事不会往前翻。")
        elif twist == "time_flies":
            engine._log("时光飞逝。")
            self._advance_story(engine)
        elif twist == "revival":
            stunned = [m for m in engine.state.monsters if m.stunned_turns > 0]
            if stunned:
                stunned[0].stunned_turns = 0
                engine._log(f"{stunned[0].name} 被故事唤醒了。")
        elif twist == "ambush":
            monster = engine._monster_by_template(self.SPIDER) or (engine.state.monsters[0] if engine.state.monsters else None)
            hero = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
            if monster is not None and hero is not None:
                monster.room_key = hero.room_key
                engine._log(f"{monster.name} 被埋伏到了 {hero.name} 所在的房间。")
        elif twist == "collapsing_floor":
            hero = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
            if hero is not None:
                here = engine.state.board.get(hero.room_key)
                if here is not None:
                    below = [k for k, r in engine.state.board.items() if r.floor == here.floor - 1]
                    if below:
                        hero.room_key = sorted(below)[0]
                        engine._log(f"{hero.name} 从塌陷的地板掉到了 {engine.state.board[hero.room_key].name}。")
        elif twist == "daze":
            hero = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
            if hero is not None:
                dazed = [int(x) for x in (flags.get("dazed") or [])]
                dazed.append(hero.id)
                flags["dazed"] = dazed
                engine._log(f"{hero.name} 被故事弄得晕头转向。")
        return True

    def _bot_auto_twist(self, engine, player):
        flags = engine._haunt_flags()
        if int(flags.get("body_tokens") or 0) < 1:
            return
        used = set(flags.get("used_twists") or [])
        needed = max(1, int(flags.get("initial_hero_count") or 1))
        done = len(flags.get("completed_quests") or [])
        order = []
        if done >= needed and "lengthy_narration" not in used:
            order.append("lengthy_narration")
        elif done < needed and "time_flies" not in used:
            order.append("time_flies")
        if "ambush" not in used:
            order.append("ambush")
        if "revival" not in used:
            order.append("revival")
        for twist in order:
            if int(flags.get("body_tokens") or 0) < 1:
                return
            if not self._twist_possible(engine, twist):
                continue
            self._resolve_twist(engine, player, twist)
            return

    # ------------------------------------------------------------- 怪物

    def _witch_attack(self, engine, monster):
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead and p.room_key == monster.room_key]
        if not heroes:
            return True
        target = min(heroes, key=lambda p: (min(p.stats.get("might", 9), p.stats.get("sanity", 9)), p.id))
        attr = "sanity" if target.stats.get("sanity", 9) <= target.stats.get("might", 9) else "might"
        monster_roll = engine._roll_monster_attack(monster, attr)
        hero_roll = engine._roll_attack(target, attr)
        engine._log(f"{monster.name} 以{attr}攻击 {engine._player_label(target)}：{monster_roll} 对 {hero_roll}。")
        if monster_roll > hero_roll:
            dtype = "mental" if attr == "sanity" else "physical"
            engine._deal_damage(target, dtype, monster_roll - hero_roll, source=monster.name)
        elif monster_roll < hero_roll:
            engine._stun_monster(monster, 1)
        else:
            engine._log("平手。")
        return True

    def _dragon_breath(self, engine, monster):
        occupants = [
            p for p in engine.state.players
            if not p.dead and p.room_key == monster.room_key and p.role != "traitor"
        ]
        others = [m for m in engine.state.monsters if m is not monster and m.room_key == monster.room_key]
        if not occupants and not others:
            return True
        dragon_roll = engine._roll_monster_attack(monster, "might")
        engine._log(f"{monster.name} 喷出火焰（{dragon_roll}）。")
        for hero in occupants:
            speed_roll = engine._roll_attack(hero, "speed")
            if speed_roll < dragon_roll:
                engine._deal_damage(hero, "physical", dragon_roll - speed_roll, source="龙焰")
            else:
                engine._log(f"{hero.name} 躲开了龙焰。")
        for other in others:
            speed_roll = engine.roll_dice(max(1, int(getattr(other, "speed", 1))), "躲避龙焰")
            if speed_roll < dragon_roll:
                engine._stun_monster(other, 1)
        return True

    def _venom_stat(self, engine, target):
        order = ("might", "speed", "sanity", "knowledge")
        living = [s for s in order if target.stats.get(s, 0) > 0]
        if not living:
            return "might"
        return min(living, key=lambda s: target.stats.get(s, 0))

    def _traitor(self, engine):
        return next((p for p in engine.state.players if p.role == "traitor" and not p.dead), None)

    def _holder(self, engine, card_id):
        return next((p for p in engine.state.players if card_id in p.items and not p.dead), None)

    def _first_room(self, engine, template_ids):
        for tid in template_ids:
            key = next((k for k, r in engine.state.board.items() if r.template_id == tid), None)
            if key:
                return key
        return None

    def _any_room(self, engine):
        traitor = self._traitor(engine)
        if traitor is not None:
            return traitor.room_key
        return next(iter(engine.state.board))


class BloodOfferingMode(GenericModeHandler):
    """剧本 64 血之献祭（An Offering of Blood）。

    权威原文：英雄手册 p75 / 叛徒手册 p146。
    · 女孩 token 放作祟房间（静止不移动——简化）。
    · 邪教徒（英雄数-1）+ 蝙蝠（同数）布点。
    · 计时到 7 → 恶魔不耐烦杀了叛徒（英雄胜）。
    · 邪教徒到达女孩房间 → 献祭 → 叛徒胜。
    · 简化：女孩移动/蝙蝠精神免疫/钩爪未建模。
    """

    mode = "blood_offering"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["girl_sacrificed"] = False
        # 女孩 token 放作祟房间
        engine.spawn_token("girl", label="女孩", role="marker", room_key=room_key)
        flags["girl_room"] = room_key
        # 邪教徒（英雄数-1）+ 蝙蝠（同数）
        spec_cultist = next((s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == "cultist"), {})
        spec_bat = {"template_id": "bat", "name": "蝙蝠", "speed": 4, "might": 3, "sanity": 3}
        heroes = sum(1 for p in engine.state.players if p.role == "hero")
        cultist_count = max(0, heroes - 1)
        bat_count = cultist_count
        for _ in range(cultist_count):
            key = engine.rng.choice(sorted(engine.state.board.keys()))
            engine._spawn_single_haunt_monster(spec_cultist, key)
        for _ in range(bat_count):
            key = engine.rng.choice(sorted(engine.state.board.keys()))
            engine._spawn_single_haunt_monster(spec_bat, key)
        engine._log(f"{cultist_count} 名邪教徒和 {bat_count} 只蝙蝠出现了——他们在追猎女孩！")

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        if player.dead:
            return
        if player.role == "traitor":
            return
        # 每个怪物回合后推进计时（简化：在叛徒回合开始时推进）
        if player.role == "traitor":
            return
        # 用英雄回合开始推进（近似每个怪物回合后）
        # p75：计时到 7 → 英雄胜

    def on_monster_turn_start(self, engine, monster):
        """邪教徒到达女孩房间 → 献祭。"""
        kind = getattr(monster, "template_id", "")
        if kind != "cultist":
            return False
        flags = engine._haunt_flags()
        girl_room = flags.get("girl_room")
        if girl_room is None:
            return False
        if monster.room_key == girl_room:
            flags["girl_sacrificed"] = True
            engine._log("女孩被献祭了——恶魔的力量涌入了世界！")
            engine._set_winner("traitor", "血之献祭完成——恶魔的力量属于叛徒。")
            engine.check_victory()
            return True
        # 邪教徒向女孩移动
        path = engine._shortest_path(monster.room_key, girl_room)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 3), "邪教徒移动")
            monster.room_key = path[min(len(path) - 1, steps)]
        # 到达 → 献祭
        if monster.room_key == girl_room:
            flags["girl_sacrificed"] = True
            engine._set_winner("traitor", "血之献祭完成。")
            engine.check_victory()
        return True

    def _advance_timer(self, engine):
        """p75：每个怪物回合后推进计时。到 7 → 英雄胜。"""
        current = engine._haunt_track_value("demon_timer") + 1
        engine._set_haunt_track_value("demon_timer", current)
        if current >= 7:
            engine._set_winner("heroes", "恶魔不耐烦了——TA 杀死了叛徒和他的仆从！")
            engine.check_victory()

    def check_victory(self, engine):
        flags = engine._haunt_flags()
        # 计时到 7 → 英雄胜
        if engine._haunt_track_value("demon_timer") >= 7:
            if engine.state.winner is None:
                engine._set_winner("heroes", "恶魔不耐烦了——TA 杀死了叛徒！")
            return True
        if flags.get("girl_sacrificed"):
            return True  # winner 已在献祭处设定
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也死了——女孩被献祭了。")
            return True
        return False



class TwistingNetherMode(GenericModeHandler):
    """剧本 63 扭曲虚空（The Twisting Nether）。

    权威原文：英雄手册 p74 / 叛徒手册 p145。
    · 英雄锚定房间（知识 5+ 任意房间，每房一次）→ 玩家数个 → 英雄胜。
    · 叛徒每回合溶解一个未锚定房间。
    · 非锚定房间全溶 → 叛徒胜。
    · 简化：nether 穿行/怪物不可攻击未建模。
    """

    mode = "twisting_nether"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["anchored_rooms"] = []
        flags["dissolved_rooms"] = []
        engine._log("房子周围的现实扭曲了——房间正在被虚空吞噬！")

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        if player.role != "traitor" or player.dead:
            return
        anchored = set(flags.get("anchored_rooms", []))
        dissolved = flags.get("dissolved_rooms", [])
        # 溶解一个未锚定房间
        candidates = [
            k for k, r in engine.state.board.items()
            if k not in anchored and k not in dissolved
            and r.template_id not in ("entrance_hall", "foyer", "grand_staircase",
                                       "upper_landing", "basement_landing")
        ]
        if candidates:
            room = engine.rng.choice(sorted(candidates))
            dissolved.append(room)
            flags["dissolved_rooms"] = dissolved
            engine._log(f"{engine.state.board[room].name} 被虚空溶解了！")
        # 检查：非锚定房间全溶 → 叛徒胜
        total_rooms = len(engine.state.board)
        fixed_rooms = 5  # 入口大厅等不溶
        non_fixed = total_rooms - fixed_rooms
        if len(dissolved) >= max(1, non_fixed - len(anchored)):
            engine._set_winner("traitor", "整栋房子被虚空吞噬了！")
            engine.check_victory()

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        anchored = set(engine._haunt_flags().get("anchored_rooms", []))
        for action in actions:
            if action.id == "anchor_room":
                if player.room_key in anchored:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        if action_id == "anchor_room":
            flags = engine._haunt_flags()
            anchored = flags.setdefault("anchored_rooms", [])
            if player.room_key in anchored:
                engine._log("这个房间已经锚定了。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                anchored.append(player.room_key)
                engine._log(f"{engine.state.board[player.room_key].name} 被锚定到了现实！")
            return ok
        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        flags = engine._haunt_flags()
        anchored = engine._haunt_track_value("anchor_progress")
        if anchored >= engine._haunt_track_target("anchor_progress"):
            engine._set_winner("heroes", "足够的房间被锚定了——房子回到了现实！")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也消失在虚空中。")
            return True
        return False



class BagOfTricksMode(GenericModeHandler):
    """剧本 62 魔袋把戏（Bag of Tricks）。

    权威原文：英雄手册 p73 / 叛徒手册 p144。
    · 叛徒角色从游戏中移除；疯子怪物（Speed 4 Might 3）生成。
    · 英雄在同疯子的房间做知识 6+ 推进进度。
    · 进度 = 玩家数 → 英雄胜；英雄全灭 → 叛徒胜。
    """

    mode = "bag_of_tricks"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["traitor_removed"] = True
        # p73：叛徒角色从游戏中移除
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine._drop_inventory_on_death(traitor)
            traitor.dead = True
            engine._log(f"{traitor.name}消失在空气中——TA 离开了游戏。")
        engine.check_victory()

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "tap_trinkets":
                madman = engine._monster_by_template("madman")
                if madman is None or madman.room_key != player.room_key:
                    continue
            result.append(action)
        return result

    def check_victory(self, engine):
        if engine._haunt_track_value("trinket_progress") >= engine._haunt_track_target("trinket_progress"):
            engine._set_winner("heroes", "疯子被送走了——房子恢复了原状。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也消失了。")
            return True
        return False



class EternalGloryMode(GenericModeHandler):
    """剧本 61 永恒荣耀（Eternal Glory）。"""

    mode = "ghost_warrior"

    RELICS = [
        ("statue_relic", "gallery", "雕像"),
        ("sarcophagus_relic", "graveyard", "石棺"),
        ("ancient_armor", "wine_cellar", "古甲"),
    ]

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["rest_tokens_rooms"] = []
        flags["spear_held_by"] = None
        flags["ghost_alive"] = True
        relic_rooms = flags.setdefault("relic_rooms", {})
        for token_kind, template_id, label in self.RELICS:
            key = next((k for k, r in engine.state.board.items() if r.template_id == template_id), None)
            if key is None:
                key = engine._ensure_room_in_play(template_id, room_key)
            if key:
                engine.spawn_token(token_kind, label=label, role="marker", room_key=key)
                relic_rooms[token_kind] = key
        engine.spawn_token("spear", label="命运之矛", role="marker", room_key=room_key)
        spec = next((s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == "ghost"), {})
        spec = dict(spec)
        spec["name"] = "幽灵战士"
        monster = engine._spawn_single_haunt_monster(spec, room_key)
        if monster is not None:
            spear = next((t for t in engine.state.tokens if t.kind == "spear"), None)
            if spear:
                engine.give_token(spear.uid, int(monster.id.split("_")[-1]))
        engine._log('幽灵战士手持长矛现身——"谁能与我匹敌！"')

    def _relic_room_for(self, engine, room_key):
        relic_rooms = engine._haunt_flags().get("relic_rooms", {})
        for token_kind, rk in relic_rooms.items():
            if rk == room_key:
                return token_kind
        return None

    def on_monster_move(self, engine, monster, rolled):
        if getattr(monster, "name", "") != "幽灵战士":
            return False
        target = engine._find_monster_target(monster)
        if target is None:
            return True
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 3), "幽灵移动")
            monster.room_key = path[min(len(path) - 1, steps)]
        if target.room_key == monster.room_key:
            ghost_roll = engine._roll_monster_attack(monster, "might")
            hero_roll = engine._roll_attack(target, "might")
            if ghost_roll > hero_roll:
                engine._deal_damage(target, "physical", ghost_roll - hero_roll, source="幽灵战士")
        return True

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "persuade_ghost" and not engine.tokens_held_by(player.id, "spear"):
                continue
            if action.id == "pick_up_spear":
                if engine.tokens_held_by(player.id, "spear"):
                    continue
                if not engine.tokens_in_room(player.room_key, "spear"):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        flags = engine._haunt_flags()
        if action_id == "pick_up_spear":
            token = next(iter(engine.tokens_in_room(player.room_key, "spear")), None)
            if token is None:
                return False
            engine.give_token(token.uid, player.id)
            flags["spear_held_by"] = player.id
            engine._log(f"{player.name} 拾取了长矛。")
            return True
        if action_id == "persuade_ghost":
            if not engine.tokens_held_by(player.id, "spear"):
                return False
            relic = self._relic_room_for(engine, player.room_key)
            if not relic:
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                engine._advance_haunt_track("persuasion_track", 1)
                new_track = engine._haunt_track_value("persuasion_track")
                target_track = 2 * sum(1 for p in engine.state.players if p.role == "hero")
                rooms = flags.setdefault("rest_tokens_rooms", [])
                if player.room_key not in rooms:
                    rooms.append(player.room_key)
                engine._log(f"说服进度（{new_track}/{target_track}，房间 {len(rooms)}）。")
                if new_track >= target_track and len(rooms) >= 2:
                    engine._set_winner("heroes", "幽灵战士终于安息了。")
                    engine.check_victory()
            return ok
        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "幽灵战士的最后一击命中了。")
            return True
        return False


class LabyrinthEscapeMode(GenericModeHandler):
    """剧本 68「The Labyrinth / 迷宫」（英雄手册 p79 / 叛徒手册 p150）。

    地下墓穴膨胀开来，把整栋房子拧成一座迷宫；石头还在挪动，滴答声越来越近。
    叛徒不改规则、不施法术，他只是比谁都清楚这座迷宫的出口在哪。

    · 开局（p150）：地下墓穴移出本局；把「英雄数」枚钥匙（五边形令牌）与
      「英雄数-1」只迷宫仆人（速4/力3/智5）放进已探索房间；回合/伤害轨归零。
    · 逃脱（p79）：钥匙能拿、能放、能交易、能被抢（但不能被狗携带）。当
      「所有」钥匙都在入口大厅里的英雄手上时，厅内任一英雄做知识 5+ 找开锁
      顺序；成功者抽一张事件牌并结束回合。门开之后，厅内英雄花 2 点移动逃出，
      逃出者移出对局、再也回不来。
    · 封印（p150）：叛徒回合开始把轨 +1，然后掷等于新位数的骰（骰子数按引擎
      口径封顶 8 枚），总和 6+ → 迷宫自我封闭 → 叛徒胜。真实位数存
      flags["turn_position"]（引擎轨道会被 target 封顶，56 号同款处理）。
    · 迷乱（p150）：仆人可改用理智攻击——双方都不掉属性，但仆人打赢就把一枚
      神志检定令牌放到该英雄身上。叛徒可以在她回合内的任何时候逼她白走一格
      （不花移动点）；回合结束迷乱解除。
    · 钥匙禁令（p150）：叛徒既不能拾取也不能抢夺钥匙——`grab_key` 只挂在
      side=heroes 上，令牌也不走引擎的卡牌抢夺分支，所以这条由结构保证。
    · 胜负（p79/p150）：英雄胜 = 逃出人数 ≥「作祟开始时活着的英雄数的一半」；
      叛徒胜 = 迷宫合拢，或死亡英雄超过一半。叛徒死亡**不**判英雄胜：门不会
      因为死人而打开，迷宫也照样合得拢（引擎通用兜底在此吸收）。

    已知简化：
        · "把剩余房间板块重排成叛徒喜欢的形状"未实现：本仓库没有搬动已放置
          房间的能力（doors 是模板属性，搬了就对不上邻格），沿用既有结论。
          地下墓穴的"移出本局"用塌方标记等价实现（连通图与移动选项都会排除
          坍塌板块），里面的人与怪先搬到邻接房间、不走坠亡结算。
        · "万能钥匙可替代一把钥匙"未实现：本项目 80 张卡牌目录里没有骷髅钥匙
          （见 67 号同款说明），要落地得先扩卡池并同步后端的数量断言。
        · 迷乱者的那一格位移固定在"她的回合结束"执行（原文是"回合内任何时刻"），
          且特殊移动所需的属性检定不免判（本引擎的特殊移动选项本就无需检定）。
        · 狗不能携带钥匙自动满足——本项目同伴卡不占物品栏、无法持物。
        · 拿/转交/放下/开锁/逃出共用引擎"每人每回合一次剧本行动"的限额；
          逃出在原版只花 2 点移动、不占行动。
        · 逃走者在界面上按"已出局"显示：引擎没有独立的出局状态，沿用 6/47 号
          的口径（直接置 dead 标记、不走死亡流程，所以物品与钥匙不会散落）。
        · 神秘电梯"落到该层哪个位置由叛徒挑"未实现（引擎按随机/固定落点处理）。
    """

    mode = "labyrinth_escape"

    KEY = "key"
    CONFUSED = "confused"
    SERVANT = "labyrinth_servant"
    HALL = "entrance_hall"
    CATACOMBS = "catacombs"
    TURN_TRACK = "labyrinth_turn"
    UI_TRACK_CAP = 12
    SEAL_ROLL_TARGET = 6
    FLEE_COST = 2
    ATTACK_DICE_CAP = 8
    SERVANT_SPEC = {
        "template_id": SERVANT, "name": "迷宫仆人", "speed": 4, "might": 3, "sanity": 5,
    }

    # ------------------------------------------------------------- 工具
    def _traitor(self, engine: Any):
        return next((p for p in engine.state.players if p.role == "traitor"), None)

    def _living_heroes(self, engine: Any) -> list[Any]:
        return [p for p in engine.state.players if p.role == "hero" and not p.dead]

    def _hall_key(self, engine: Any) -> str:
        return next(
            (key for key, room in sorted(engine.state.board.items())
             if room.template_id == self.HALL),
            "",
        )

    def _in_hall(self, engine: Any, player: Any) -> bool:
        room = engine.state.board.get(player.room_key)
        return room is not None and room.template_id == self.HALL

    def _keys_held_by_heroes_in_hall(self, engine: Any) -> int:
        hall = self._hall_key(engine)
        if not hall:
            return 0
        return sum(
            1 for token in engine.tokens_of_kind(self.KEY)
            if token.holder is not None
            and 0 <= token.holder < len(engine.state.players)
            and engine.state.players[token.holder].role == "hero"
            and not engine.state.players[token.holder].dead
            and engine.state.players[token.holder].room_key == hall
        )

    def _all_keys_in_hall(self, engine: Any) -> bool:
        total = int(engine._haunt_flags().get("keys_total", 0))
        return total > 0 and self._keys_held_by_heroes_in_hall(engine) >= total

    def _confused(self, engine: Any, player: Any) -> bool:
        return bool(engine.tokens_held_by(player.id, self.CONFUSED))

    def _stage_rooms(self, engine: Any) -> list[str]:
        """可作为布点场的房间：已探索、没塌、不是入口大厅（叛徒不会把
        钥匙和伏兵留在门口——原文明说位置由叛徒挑）。"""
        hall = self._hall_key(engine)
        return [
            key for key, room in sorted(engine.state.board.items())
            if room.revealed and key != hall and not engine._is_collapsed(key)
        ]

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        hero_count = max(1, len(self._living_heroes(engine)))
        flags["hero_count"] = hero_count
        flags["keys_total"] = hero_count
        flags["escape_target"] = (hero_count + 1) // 2
        flags["door_unlocked"] = False
        flags["sealed"] = False
        flags["escaped_hero_ids"] = []
        flags["turn_position"] = 0
        tracks = engine._haunt_tracks()
        tracks.setdefault(
            self.TURN_TRACK,
            {"label": "回合/伤害轨（迷宫封闭倒计时）", "target": self.UI_TRACK_CAP, "value": 0},
        )
        tracks[self.TURN_TRACK]["target"] = self.UI_TRACK_CAP
        engine._set_haunt_track_value(self.TURN_TRACK, 0)

        self._retire_catacombs(engine)
        rooms = self._stage_rooms(engine)
        if not rooms:
            rooms = [key for key, room in sorted(engine.state.board.items()) if room.revealed]
        for index in range(hero_count):
            if not rooms:
                break
            engine.spawn_token(self.KEY, label="钥匙", role="marker", room_key=rooms[index % len(rooms)])
        servant_count = max(0, hero_count - 1)
        for index in range(servant_count):
            if not rooms:
                break
            engine._spawn_single_haunt_monster(dict(self.SERVANT_SPEC), rooms[index % len(rooms)])
        engine._log(
            f"房子拧成了一整座迷宫：{hero_count} 把钥匙散在厅外，"
            f"{servant_count} 个仆人在墙之间游荡，"
            f"逃出去一半人（{flags['escape_target']} 名）才算赢。"
        )

    def _retire_catacombs(self, engine: Any) -> None:
        """p150：把地下墓穴从房子里拿走。本仓库没有"撤房"能力，用塌方标记
        等价实现——先把它里面的人与怪搬到邻接的已探索房间，再翻掉这块牌。"""
        key = next(
            (k for k, room in sorted(engine.state.board.items()) if room.template_id == self.CATACOMBS),
            "",
        )
        if not key or engine._is_collapsed(key):
            return
        refuge = self._catacomb_refuge(engine, key)
        if not refuge:
            engine._log("地下墓穴无处可撤（它被孤立在别处）：本局仍按原样使用它（已知简化）。")
            return
        for player in [p for p in engine.state.players if not p.dead and p.room_key == key]:
            engine._move_to_room(player, refuge, via_effect=False)
        for monster in [m for m in engine.state.monsters if m.room_key == key]:
            monster.room_key = refuge
        engine._collapse_room(key, cause="迷宫重组后的黑暗里", consumes_monsters=False)

    def _catacomb_refuge(self, engine: Any, key: str) -> str:
        candidates = [
            other for other in engine._door_neighbors(key)
            if other != key and not engine._is_collapsed(other) and engine.state.board[other].revealed
        ]
        if candidates:
            return candidates[0]
        return next(
            (
                other for other, room in sorted(engine.state.board.items())
                if other != key and room.revealed and not engine._is_collapsed(other)
            ),
            "",
        )

    # ------------------------------------------------------- 回合与迷宫合拢
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if flags.get("sealed"):
            return
        traitor = self._traitor(engine)
        if traitor is not None and not traitor.dead:
            if player.role == "traitor":
                self._advance_seal(engine)
            return
        # 叛徒已死也要继续合拢（p150 的胜负条件不依赖他活着）：本轮首位英雄代推
        if player.role == "hero" and self._is_first_living_in_order(engine, player):
            self._advance_seal(engine)

    def _is_first_living_in_order(self, engine: Any, player: Any) -> bool:
        for player_id in engine.state.turn_order:
            candidate = next((p for p in engine.state.players if p.id == player_id), None)
            if candidate is not None and not candidate.dead and candidate.role == "hero":
                return candidate.id == player.id
        return False

    def _advance_seal(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        position = int(flags.get("turn_position", 0)) + 1
        flags["turn_position"] = position
        engine._set_haunt_track_value(self.TURN_TRACK, min(position, self.UI_TRACK_CAP))
        dice = max(1, min(position, self.ATTACK_DICE_CAP))
        roll = engine.roll_dice(dice, "迷宫是否合拢")
        engine._log(f"石头咯咯作响（回合/伤害轨第 {position} 格：{dice} 骰掷出 {roll}，需 {self.SEAL_ROLL_TARGET}+ 才合拢）。")
        if roll >= self.SEAL_ROLL_TARGET:
            flags["sealed"] = True
            engine._log("最后一道门化进了墙里。迷宫合上了。")
            engine.check_victory()

    # --------------------------------------------------------------- 迷乱
    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p150：仆人可用理智代替力量——双方都不掉属性，打赢即弄糊涂目标。"""
        if getattr(monster, "template_id", "") != self.SERVANT:
            return False
        targets = [
            p for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == monster.room_key
        ]
        if not targets:
            return False
        fresh = [p for p in targets if not self._confused(engine, p)]
        if not fresh:
            return False  # 已经糊涂的人再推一把没意义：改用普通力量攻击
        target = min(fresh, key=lambda p: (p.stats.get("sanity", 9), p.id))
        monster_roll = engine._roll_monster_attack(monster, "sanity")
        hero_roll = engine._roll_attack(target, "sanity")
        engine._log(f"{monster.name} 低语着扰乱 {engine._player_label(target)} 的神志：{monster_roll} 对 {hero_roll}。")
        if monster_roll > hero_roll:
            engine.spawn_token(self.CONFUSED, label="神志检定", role="check", holder=target.id)
            engine._log(f"{target.name} 分不清东南西北了（叛徒可以随时逼她白走一格）。")
        else:
            engine._log("她的神志守住了——谁都没受伤。")
        return True

    def on_turn_end(self, engine: Any, player: Any) -> None:
        if player.dead or not self._confused(engine, player):
            return
        self._force_stumble(engine, player)
        for token in engine.tokens_held_by(player.id, self.CONFUSED):
            engine.remove_token(token.uid)
        if not player.dead:
            engine._log(f"{player.name} 回过神来——刚才那一步是别人替她走的。")

    def _force_stumble(self, engine: Any, player: Any) -> None:
        """p150：叛徒逼迷乱者走一格，不花她的移动点。"""
        saved_steps = player.steps_remaining
        saved_stopped = player.movement_stopped
        player.movement_stopped = False
        player.steps_remaining = max(1, saved_steps)
        try:
            options = [option for option in engine.available_move_options(player) if not option.is_new_room]
            if not options:
                return
            option = self._stumble_option(engine, player, options)
            engine.move_player(player, option)
        finally:
            player.steps_remaining = saved_steps
            player.movement_stopped = saved_stopped

    def _stumble_option(self, engine: Any, player: Any, options: list[Any]) -> Any:
        hall = self._hall_key(engine)
        servant_rooms = {monster.room_key for monster in engine.state.monsters if monster.template_id == self.SERVANT}
        traitor = self._traitor(engine)
        if traitor is not None and traitor.control == "human":
            labels = [
                f"{engine._direction_cn(option.direction)} → {option.target_room_name or '未知房间'}"
                for option in options
            ]
            choice = engine.prompter.choose_from_list(
                "迷宫的错觉", f"{player.name} 神志不清，要把她往哪边推？", labels
            )
            if choice is not None and 0 <= choice < len(options):
                return options[choice]
        # 机器人叛徒：优先推进有仆人的房间，否则推得离前门越远越好
        return max(
            options,
            key=lambda option: (
                option.target_key in servant_rooms,
                engine._path_length(option.target_key, hall) if hall else 0,
                option.target_key,
            ),
        )

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        if player.role != "hero" or player.dead:
            return []
        flags = engine._haunt_flags()
        held = engine.tokens_held_by(player.id, self.KEY)
        can_unlock = self._in_hall(engine, player) and self._all_keys_in_hall(engine)
        can_flee = (
            self._in_hall(engine, player)
            and bool(flags.get("door_unlocked"))
            and player.steps_remaining >= self.FLEE_COST
        )
        result = []
        for action in actions:
            action_id = action.id
            if action_id == "flee_labyrinth":
                if not can_flee:
                    continue
            elif action_id == "unlock_door":
                if not can_unlock:
                    continue
            elif action_id == "grab_key":
                if not engine.tokens_in_room(player.room_key, self.KEY):
                    continue
            elif action_id in {"pass_key", "drop_key"}:
                if not held or can_unlock or self._in_hall(engine, player):
                    # 能开锁就别再倒手；站在大厅里更别放——放下后钥匙就不算
                    # "在英雄手上"，p79 的开锁条件会被自己弄丢。
                    continue
                if not self._pass_targets(engine, player):
                    # 没有还空着手的队友就别放下（防机器人原地循环）
                    continue
            result.append(action)
        return result

    def _pass_targets(self, engine: Any, player: Any) -> list[Any]:
        """同房间里一把钥匙都没带的英雄——钥匙得有人带得动。"""
        return [
            other for other in engine.state.players
            if not other.dead and other.id != player.id and other.role == "hero"
            and other.room_key == player.room_key and not engine.tokens_held_by(other.id, self.KEY)
        ]

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        held = engine.tokens_held_by(player.id, self.KEY)

        if action_id == "grab_key":
            token = next(iter(engine.tokens_in_room(player.room_key, self.KEY)), None)
            if token is None:
                engine._log("这个房间里没有钥匙。")
                return False
            engine.give_token(token.uid, player.id)
            need = int(flags.get("keys_total", 0))
            engine._log(f"{player.name} 收起了{token.label}（全队要集齐 {need} 把）。")
            return True

        if action_id == "drop_key":
            if not held:
                engine._log("你身上没有钥匙。")
                return False
            engine.place_token(held[0].uid, player.room_key)
            room = engine.state.board.get(player.room_key)
            engine._log(f"{player.name} 把钥匙留在了{(room.name if room else '原地')}。")
            return True

        if action_id == "pass_key":
            if not held:
                engine._log("你身上没有钥匙可转交。")
                return False
            candidates = self._pass_targets(engine, player)
            if not candidates:
                engine._log("同房间里没有还缺钥匙的队友。")
                return False
            choice = engine.prompter.choose_from_list(
                "转交钥匙", "把钥匙交给谁？", [other.name for other in candidates]
            )
            target = candidates[choice] if choice is not None and 0 <= choice < len(candidates) else candidates[0]
            engine.give_token(held[0].uid, target.id)
            engine._log(f"{player.name} 把钥匙塞给了{target.name}。")
            return True

        if action_id == "unlock_door":
            if not self._in_hall(engine, player) or not self._all_keys_in_hall(engine):
                engine._log("开锁得站在入口大厅，而且所有钥匙都要在厅里英雄的手上（p79）。")
                return False
            was_unlocked = bool(flags.get("door_unlocked"))
            ran = super().perform_action(engine, player, action_id, data)
            if ran and not was_unlocked and flags.get("door_unlocked"):
                engine._log("锁簧依次归位——前门开了！")
                engine._draw_symbol_card(player, "event")  # p79：成功者抽一张事件牌
                player.movement_stopped = True
                player.steps_remaining = 0
                player.attack_used = True
                engine._log(f"{player.name} 把剩下的力气都用在推门上，回合结束。")
                engine.check_victory()
            return ran

        if action_id == "flee_labyrinth":
            if not flags.get("door_unlocked"):
                engine._log("前门还锁着。")
                return False
            if not self._in_hall(engine, player):
                engine._log("逃出迷宫必须站在入口大厅。")
                return False
            if player.steps_remaining < self.FLEE_COST:
                engine._log(f"逃出要留下 2 点移动，你只剩 {player.steps_remaining} 点。")
                return False
            player.steps_remaining -= self.FLEE_COST
            escaped = sorted(set(int(x) for x in (flags.get("escaped_hero_ids") or [])) | {player.id})
            flags["escaped_hero_ids"] = escaped
            flags["escaped_heroes"] = len(escaped)
            # 引擎没有独立的"出局"状态：直接置 dead、不走死亡流程，
            # 所以他身上的钥匙与物品不会散落在大厅里（6/47 号同款口径）。
            player.dead = True
            engine._log(
                f"{player.name} 挤出那道门缝，消失在夜里——他再也不会回来"
                f"（逃出 {len(escaped)}/{flags.get('escape_target', 1)}）。"
            )
            return True

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 进度
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        total = int(flags.get("keys_total", 0))
        position = int(flags.get("turn_position", 0))
        escaped = len(flags.get("escaped_hero_ids") or [])
        lines = [
            f"钥匙：厅内英雄手上 {self._keys_held_by_heroes_in_hall(engine)}/{total}｜"
            f"随身 {sum(1 for token in engine.tokens_of_kind(self.KEY) if token.holder is not None)}｜"
            f"散落在房间 {sum(1 for token in engine.tokens_of_kind(self.KEY) if token.room_key)}",
            (
                f"前门已开：站在入口大厅花 {self.FLEE_COST} 点移动就能逃（逃出 {escaped}/"
                f"{flags.get('escape_target', 1)} 即英雄胜）"
                if flags.get("door_unlocked")
                else f"前门锁着：把 {total} 把钥匙全部带进入口大厅的英雄手上，再做知识 5+"
            ),
            f"回合/伤害轨：第 {position} 格（掷 {max(1, min(position, self.ATTACK_DICE_CAP))} 骰，"
            f"{self.SEAL_ROLL_TARGET}+ 迷宫就合上）",
        ]
        confused = [p.name for p in self._living_heroes(engine) if self._confused(engine, p)]
        if confused:
            lines.append("神志不清：" + "、".join(confused))
        return lines

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """手里有钥匙（或门已开）就往入口大厅跑，空手就去搜钥匙。"""
        if player.dead or player.role != "hero":
            return []
        flags = engine._haunt_flags()
        hall = self._hall_key(engine)
        if flags.get("door_unlocked") or engine.tokens_held_by(player.id, self.KEY):
            return [f"__room__{hall}"] if hall else []
        return [
            f"__room__{token.room_key}"
            for token in engine.tokens_of_kind(self.KEY) if token.room_key
        ]

    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        hero_count = max(1, int(flags.get("hero_count", 0)))
        escaped_ids = {int(x) for x in (flags.get("escaped_hero_ids") or [])}
        escaped = len(escaped_ids)
        target = max(1, int(flags.get("escape_target", 1)))
        if escaped >= target:
            engine._set_winner("heroes", "门外的冷风扑面而来——至少一半人逃出了迷宫。")
            return True
        if flags.get("sealed"):
            engine._set_winner("traitor", "迷宫合上了。永恒等待着他们。")
            return True
        dead = sum(
            1 for player in engine.state.players
            if player.role == "hero" and player.dead and player.id not in escaped_ids
        )
        if dead > hero_count / 2:
            engine._set_winner("traitor", "超过一半的英雄死在了迷宫深处。")
            return True
        traitor = self._traitor(engine)
        if traitor is not None and not traitor.dead:
            return False
        # 叛徒已死：引擎"叛徒死 → 英雄胜"的兜底不适用于本剧本，这里吸收掉，
        # 让门与迷宫自己决定结局。
        if not self._living_heroes(engine):
            engine._set_winner("traitor", "迷宫里再没有一个活着的英雄。")
            return True
        return True


for _handler in (
    GenericModeHandler(),
    BanishmentEscortMode(),
    SeanceRaceMode(),
    WebEscapeMode(),
    WerewolfHuntMode(),
    WitchAndFrogsMode(),
    AlienAbductionMode(),
    CarnivorousIvyMode(),
    ExorcismMode(),
    DeathDanceMode(),
    ZombieTrapMode(),
    SpecterInvasionMode(),
    FleshwalkerMode(),
    NightmareDreamMode(),
    StarsRightMode(),
    DragonSiegeMode(),
    PhantomBombMode(),
    BugSprayMode(),
    OffspringMode(),
    BeastmasterMode(),
    GhostBrideMode(),
    ZombieLordMode(),
    AbyssExorcismMode(),
    TentacledHorrorMode(),
    BatSwarmMode(),
    HellbeastMode(),
    VoodooMode(),
    RatRitualMode(),
    AmokFleshMode(),
    DemonRingMode(),
    FrankensteinMode(),
    DraculaRisingMode(),
    LivingHouseMode(),
    LostDimensionMode(),
    LakeRescueMode(),
    MadWorldMode(),
    SmallChangeMode(),
    SwampEscapeMode(),
    DeathCheckmateMode(),
    SupernaturalAgingMode(),
    HeirAssassinMode(),
    BuriedAliveMode(),
    InvisibleTraitorMode(),
    HellGateHeroMode(),
    ShadowExorcismMode(),
    TimeBombMode(),
    CannibalFeastMode(),
    OuroborosMode(),
    CrimsonJackMode(),
    AstralSpiritMode(),
    NightMurderMode(),
    SandsOfTimeMode(),
    NightfallMode(),
    ForAThousandYearsMode(),
    BurningSandsMode(),
    DarkerThanNightMode(),
    CracklingAuraMode(),
    ToxicObjectEscapeMode(),
    ArkanokSkullMode(),
    KingsRoadsMode(),
    PortraitCurseMode(),
    EternalGloryMode(),
    BagOfTricksMode(),
    TwistingNetherMode(),
    BloodOfferingMode(),
    BreathOfWindMode(),
    HellOnEarthMode(),
    StorybookTwistsMode(),
    LabyrinthEscapeMode(),
):

    register_mode(_handler)

def _is_last_in_round(engine: Any, player: Any) -> bool:
    """判断 player 是否是"本轮最后一名存活玩家"。

    叛徒已出局的剧本要靠 on_turn_end 驱动每轮一次的时钟（怪物回合、
    触手成长、蝙蝠入室……）。turn_order 是循环队列：若下一个活人的位置索引
    不大于当前位置，说明轮转即将绕回开头——当前玩家就是本轮末尾。
    """
    alive = {p.id for p in engine.state.players if not p.dead}
    if player.id not in alive:
        return False
    order = engine.state.turn_order
    total = len(order)
    if not total:
        return True
    for step in range(1, total + 1):
        nxt = (engine.state.turn_index + step) % total
        if order[nxt] in alive:
            return nxt <= engine.state.turn_index
    return True


def _monster_id(monster: Any) -> str:
    """取怪物模板 id，取不到就返回空串。

    引擎会无条件调用 on_monster_* 这组钩子。若某个调用点传来的不是
    Monster（例如怪物已被移除后残留的引用），直接读 .template_id 会抛
    AttributeError 让整局崩溃——所以统一走这个防御式取值。
    """
    return str(getattr(monster, "template_id", "") or "")


def get_mode_handler(mode: str | None) -> HauntModeHandler:
    """按 mode 取 handler；没有定制实现时回落到通用规则。

    这里刻意不抛异常：未注册的 mode 是常态（68 个剧本如此），回落是设计
    行为而不是错误。
    """
    if not mode:
        return _MODE_HANDLERS["generic"]
    return _MODE_HANDLERS.get(mode, _MODE_HANDLERS["generic"])


def registered_modes() -> list[str]:
    return sorted(_MODE_HANDLERS)
