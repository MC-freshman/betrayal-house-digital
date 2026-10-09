"""SeanceRaceMode（剧本 2）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


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

    # ------------------------------------------------------------- 地点豁免
    def action_room_override(self, engine: Any, player: Any, action: dict) -> bool:
        """p84：叛徒持有通灵板时，可以在**任何地方**举行降灵会。

        rule_data 的 rooms 对双方一视同仁（五芒星室），但叛徒手册写得清楚：
        "当你持有通灵板时，可以尝试知识检定或理智检定"——地点不受限。
        没有这条豁免，叛徒被锁死在五芒星室里、英雄则因为房间里降不了灵
        原地打转（seed101/4p 实测：五芒星室没被探出，零剧本行动）。
        """
        return (
            str(action.get("id")) == "seance_check"
            and player.role == "traitor"
            and "omen_spirit_board" in player.items
        )

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """降灵会还没出结果时，找骨头/安葬的房间不算寻路目标。

        `find_bones` / `bury_bones` 的门槛写在 `requires`（`flag:ghost_summoned`
        且 `flag:ghost_control=heroes`），而机器人的目标计算只看行动声明的
        `rooms`——只要协议里列了阁楼/卧室/主卧/地窖/墓地，英雄从作祟第一回合
        就朝这些房间走。站进"目标房间"后再也没有移动加分，整个人钉在原地：
        五芒星室（降灵会唯一场地）永远没人去，`hero_seance` 卡在 0/2。实测
        seed63/4p 打满 300 回合、同一房间往返 640 步、降灵进度全程为 0。

        本钩子在 `bot_ai._haunt_goal_targets` 里也会被调用（用来剔除不作为
        目标的行动），所以这一条同时修正"机器人选什么行动"和"机器人往哪走"。
        """
        if action_id not in ("find_bones", "bury_bones"):
            return False
        flags = engine._haunt_flags()
        if not flags.get("ghost_summoned") or flags.get("ghost_control") != "heroes":
            # p13：两条都是"If You Summon the Ghost First"之后的任务；
            # 叛徒控鬼时安葬已失效（只剩摧毁幽灵一条路）。
            return True
        if action_id == "find_bones":
            return bool(flags.get("bones_found"))
        return not flags.get("bones_found")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        # 英雄手册 p13：知识与理智检定令牌各"玩家数"枚，另有幽灵与尸体令牌
        count = len(engine.state.players)
        engine.spawn_tokens("knowledge_check", count, label="知识检定", role="check")
        engine.spawn_tokens("sanity_check", count, label="理智检定", role="check")
        # 叛徒手册 p84：若五芒星室不在屋内，叛徒要在房间牌堆里找出它放进屋，
        # "放在距你至少五格远的地方（若没有，就尽量远）"。缺这条时英雄永远
        # 无法举行降灵会——seed101/4p 实测五芒星室整局没出现、零剧本行动、
        # 机器人在内庭原地打转 133 次，300 回合打不完。
        # 简化：原版要求"地下室门口旁"，引擎按模板楼层（地面层）挑空位，
        # 只保留"尽量远离叛徒"这一半。
        revealer_id = engine.state.haunt_revealer_id
        origin = room_key
        if revealer_id is not None and 0 <= int(revealer_id) < len(engine.state.players):
            origin = engine.state.players[int(revealer_id)].room_key
        if engine._ensure_room_in_play(
            "pentagram_chamber", origin_room_key=None, farthest_from_key=origin
        ) is None:
            engine._log("房间牌堆里已经找不到五芒星室了，降灵会只能另想办法。")

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
        options = ["知识检定", "理智检定"]
        if player.role == "traitor":
            has_k = int(flags.get("traitor_seance_knowledge", 0)) > 0
            has_s = int(flags.get("traitor_seance_sanity", 0)) > 0
            if has_k and not has_s:
                options = ["理智检定"]
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
    def _is_last_alive_hero_of_round(self, engine: Any, player: Any) -> bool:
        """当前玩家是不是"本轮最后一位存活英雄"（判定方式与引擎怪物回合代理一致）。

        turn_order 是循环队列：往后找下一个活人，如果位置绕回了开头，
        说明当前玩家就是本轮末尾。
        """
        order = engine.state.turn_order
        if not order:
            return True
        alive = {p.id for p in engine.state.players if not p.dead and p.role == "hero"}
        if player.id not in alive:
            return False
        total = len(order)
        index = engine.state.turn_index
        for step in range(1, total + 1):
            next_index = (index + step) % total
            if order[next_index] in alive:
                return next_index <= index
        return True

    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if flags.get("ghost_control") != "heroes" or flags.get("bones_buried"):
            return
        owner = flags.get("seance_owner_id")
        if owner is None:
            return
        owner_alive = any(p.id == int(owner) and not p.dead for p in engine.state.players)
        if owner_alive:
            if player.id != int(owner):
                return
        elif not self._is_last_alive_hero_of_round(engine, player):
            # 降灵主人已经死了：倒计时改由"本轮最后一位存活英雄"代跑，
            # 每轮推进一次。不代理的话它会永久冻结（seed113/4p 实测停在
            # 1/5），英雄没有时间压力、叛徒也永远等不到"逾期夺权"。
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
