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

    def movement_cost_floor(self, engine: Any, player: Any, from_key: str | None = None) -> int:
        """玩家移动费用的下限（剧本 17：蟑螂守厨房时离开按 3 格计）。"""
        return 0

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """攻击落败时是否免除攻击者受到的反击伤害（剧本 17：用杀虫剂落败不受伤）。"""
        return False

    def special_steal(self, engine: Any, attacker: Any, target: Any, diff: int, attack_attr: str) -> bool:
        """剧本自定义的特殊偷取（剧本 19：>2 伤害偷走长矛）。返回 True 表示已处理。"""
        return False

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

    def room_entry_blocked(self, engine: Any, player: Any, room: Any) -> bool:
        """该玩家是否禁止进入/探索该房间（剧本 26：英雄与老鼠进不了五芒星室）。

        引擎在两处调用：`available_move_options` 过滤已有的相邻房间选项；
        探索新房间抽牌时若抽到被禁的模板则弃掉重抽。room 可能是 PlacedRoom
        也可能是 RoomTemplate（探索场景），判断时读 template_id / id 即可。
        """
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

    def movement_cost_floor(self, engine: Any, player: Any, from_key: str | None = None) -> int:
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
    VoodooMode(),
    RatRitualMode(),
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
