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
