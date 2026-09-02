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


class BanishmentEscortMode(GenericModeHandler):
    """剧本 1 木乃伊苏醒（The Mummy Walks）。

    权威原文：英雄手册 p12 / 叛徒手册 p83。

    已核对且原本就正确的部分：
        木乃伊属性 Speed 3 / Might 8 / Sanity 5；两步调查均为 Knowledge 6+；
        放逐需 2 枚知识检定令牌 + 持书与木乃伊同房间打理智战。
    本次补齐的是此前完全缺失的令牌链路：
        石棺/木乃伊/女孩三个令牌的放置、女孩拾取、关键牌不在场时补抽。
    仍未实现（需改战斗与移动结算，风险较高，已单独立项）：
        木乃伊造成速度伤害直到对手速度触底（但不降到骷髅）后转为力量伤害；
        单次造成 2+ 伤害时可改为夺取物品或抢走女孩；
        移动掷出 0 或 1 时可经秘密通道移动到屋内任意位置。
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
    幽灵穿墙移动、英雄控灵期间幽灵不攻击。
    已知简化：叛徒控灵引发"房屋坍塌"未实现（需要房间翻转/相邻性/
    死亡整套系统，规模较大，单独立项）；"降灵完成前禁止攻击"未实现。
    """

    mode = "seance_race"

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
        · 女巫法术：蛙皮（同房间理智对决变蛙）、鸦翼（飞向最近英雄）
        · 青蛙状态：掉物品、力量/知识降到最低格（不降骷髅），
          不能攻击/抽牌/探索；复原时属性回到角色卡初始值
        · 猫：第一个蛙出现后生成于作祟房间，追最近的蛙，力量对决吃掉

    已知简化：
        · 龙息（视线内 2 骰物理伤害）未实现——引擎的怪物攻击只在同房间
          触发，视线攻击需要新的怪物回合结构
        · 蛙不能被拾取携带（原文可像物品一样被背走）——先让蛙留在房间，
          救人须到蛙所在房间施法
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
        result = []
        for action in actions:
            if action.id == "dig_root" and not engine.tokens_in_room(player.room_key, "root"):
                continue  # p14：只有在长着曼德拉草的房间才能挖
            if action.id == "cast_mortal_form" and not engine.tokens_held_by(player.id, "root"):
                continue  # 施法需要曼德拉草
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
            return ok

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

    已知简化：蜘蛛"重掷空白骰"未实现（引擎掷骰无重掷概念）；
    "抽事件卡并结束回合后下一回合才能出门"简化为开门后下一回合出门。
    """

    mode = "web_escape"

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
        # 英雄全灭 / 叛徒阵亡等兜底交给引擎
        return False


for _handler in (
    GenericModeHandler(),
    BanishmentEscortMode(),
    SeanceRaceMode(),
    WebEscapeMode(),
    WerewolfHuntMode(),
    WitchAndFrogsMode(),
    AlienAbductionMode(),
    CarnivorousIvyMode(),
):
    register_mode(_handler)


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
