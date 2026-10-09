"""BloodOfferingMode（剧本 64）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _is_last_in_round,
)


class BloodOfferingMode(GenericModeHandler):
    """剧本 64 血之献祭（An Offering of Blood）。

    权威原文：英雄手册 p75 / 叛徒手册 p146。

    机制（逐条对照原文）：
      · 开局：女孩 token 放进作祟房间（揭示者手上的女孩预兆卡归位）；计时轨归零。
      · 邪教徒 = 英雄数 - 1，布点按原文「距最近英雄至少 4 格、每层人数不超过
        该层英雄数、做不到就放到尽可能远」。
      · 英雄胜线（p75）：**每个怪物回合结束后计时轨 +1，到 7 时恶魔不耐烦，
        叛徒与他的仆从一起消失**——即英雄需要撑满 7 个怪物回合。
      · 叛徒胜线（p146）：女孩每次被力量/速度攻击打中，女孩卡上添一枚力量令牌；
        累计 5 枚女孩死亡，叛徒获胜（被理智攻击击败只会让她昏迷，不计数）。
      · 邪教徒：在带预兆符号的房间代替攻击做知识 5+ → 打开传送门
        （知识检定令牌）；在已有传送门的房间代替攻击做知识检定召唤蝙蝠：
        8+ 3 只 / 5-7 2 只 / 3-4 1 只 / 0-2 无。
      · 英雄可以同房做知识 4+ 关闭传送门。
      · 特殊攻击：蝙蝠受到物理伤害即死（不击晕）；邪教徒照常击晕。

    已知简化：
      · 女孩在电子版静止不动（原文由揭示者像怪物一样掷骰移动），
        所以"移动女孩逃命"这条战术不存在，双方都围着固定点位打。
      · 钩爪（原文女孩被钩爪之类的特殊交互）与女孩被理智攻击后"昏迷一回合"
        只记 flag，不取消她的存在感。
      · 蝙蝠「召唤当回合半速移动、不能攻击」未建模（新蝙蝠下一回合才轮到行动，
        与原文的差别只在召唤当回合）。
      · 「对左轮防御多掷一骰」未建模（引擎没有武器专属防御加值入口）。
    """

    mode = "blood_offering"

    GIRL_MIGHT = 3
    GIRL_SPEED = 3
    MAX_BATS = 24  # p146：原版配件一共 24 枚蝙蝠令牌
    BAT_SPEC = {"template_id": "bat", "name": "蝙蝠", "speed": 4, "might": 3, "sanity": 3}

    # ------------------------------------------------------------- 工具
    def _girl_room(self, engine: Any) -> str | None:
        room_key = engine._haunt_flags().get("girl_room")
        return room_key or None

    def _portals(self, engine: Any) -> list[Any]:
        return engine.tokens_of_kind("knowledge_check")

    def _cultist_spots(self, engine: Any, count: int) -> list[str]:
        """p146：距最近英雄 ≥4 格、每层不超过该层英雄数（做不到就放到尽量远）。"""
        board = engine.state.board
        if not board or count <= 0:
            return []
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return [sorted(board)[0]] * count

        def distance(key: str) -> int:
            return min((engine._path_length(key, h.room_key) for h in heroes), default=9999)

        hero_per_floor: dict[int, int] = {}
        for hero in heroes:
            room = board.get(hero.room_key)
            if room is not None:
                hero_per_floor[room.floor] = hero_per_floor.get(room.floor, 0) + 1

        chosen: list[str] = []
        for min_distance in (4, 3, 2, 1, 0):
            for key in sorted(board, key=lambda k: (-distance(k), k)):
                if len(chosen) >= count or key in chosen:
                    continue
                if distance(key) < min_distance:
                    continue
                floor = board[key].floor
                cap = max(1, hero_per_floor.get(floor, 1))
                if sum(1 for c in chosen if board[c].floor == floor) >= cap:
                    continue
                chosen.append(key)
            if len(chosen) >= count:
                break
        while len(chosen) < count:
            chosen.append(sorted(board)[0])
        return chosen[:count]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["girl_room"] = room_key
        flags["girl_dead"] = False
        flags["girl_stunned"] = 0
        flags["girl_pending"] = []
        room = engine.state.board.get(room_key)
        flags["haunt_floor"] = room.floor if room is not None else -1
        engine.spawn_token("girl", label="女孩", role="marker", room_key=room_key)
        engine._set_haunt_track_value("demon_timer", 0)
        engine._set_haunt_track_value("girl_wounds", 0)

        # p75：揭示者失去女孩预兆卡（卡本身留在场外，不再提供加值）
        revealer = next(
            (p for p in engine.state.players if p.id == engine.state.haunt_revealer_id), None
        )
        if revealer is not None and "omen_girl" in revealer.items:
            engine._discard_card_from_player(revealer, "omen_girl", return_to_room=False)

        heroes = sum(1 for p in engine.state.players if p.role == "hero")
        cultist_count = max(0, heroes - 1)
        spec_cultist = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == "cultist"), {}
        )
        for key in self._cultist_spots(engine, cultist_count):
            engine._spawn_single_haunt_monster(spec_cultist, key)
        engine._log(f"{cultist_count} 名邪教徒在屋里四处张望——他们要把女孩献出去！")

    # ------------------------------------------------------------- 生命周期
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if int(flags.get("girl_stunned", 0)) > 0:
            flags["girl_stunned"] = int(flags["girl_stunned"]) - 1

    def on_turn_end(self, engine: Any, player: Any) -> None:
        """p75：每个怪物回合结束后计时 +1——用「本轮最后一名玩家」当那根指针。"""
        if not _is_last_in_round(engine, player):
            return
        self._advance_timer(engine)

    def _advance_timer(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        flags["summoned_rooms"] = []  # 新一轮：每道传送门又能被召唤一次
        if flags.get("girl_dead"):
            return
        current = engine._advance_haunt_track("demon_timer", 1)
        engine._log(f"恶魔开始不耐烦了（{current}/7）。")
        if current >= 7:
            engine._set_winner("heroes", "恶魔失去了耐心——它把叛徒和他的仆从一起拖回了地狱。")

    # ------------------------------------------------------------- 怪物回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        kind = getattr(monster, "template_id", "")
        if kind != "cultist":
            return False
        flags = engine._haunt_flags()
        if flags.get("girl_dead"):
            return False
        room_key = monster.room_key
        room = engine.state.board.get(room_key)
        knowledge = int(getattr(monster, "knowledge", 0) or 5)

        # p146：已有传送门的房间 → 召唤蝙蝠（代替攻击）
        if engine.tokens_in_room(room_key, "knowledge_check"):
            # 原文："Only one Cultist can summon bats from a given portal each
            # turn." —— 同一道传送门每回合只允许一只邪教徒召唤。不设这一条时
            # 三只邪教徒各自开一扇门、每回合各召 1-3 只，蝙蝠会滚成雪球
            # （批次 13 实测 seed109/5p 场上 13 只怪，英雄 23 回合全灭）。
            used = flags.setdefault("summoned_rooms", [])
            if room_key in used:
                return True
            if sum(1 for m in engine.state.monsters if getattr(m, "template_id", "") == "bat") >= self.MAX_BATS:
                return True
            used.append(room_key)
            roll = engine.roll_dice(max(1, min(8, knowledge)), "召唤蝙蝠")
            count = 3 if roll >= 8 else (2 if roll >= 5 else (1 if roll >= 3 else 0))
            for _ in range(count):
                engine._spawn_single_haunt_monster(dict(self.BAT_SPEC), room_key)
            if count:
                engine._log(f"邪教徒从传送门里唤出 {count} 只蝙蝠！")
            else:
                engine._log("邪教徒低声念咒，但传送门里什么都没出来。")
            return True

        # p146：带预兆符号的房间 → 开传送门（代替攻击）
        if room is not None and room.symbol == "omen":
            roll = engine.roll_dice(max(1, min(8, knowledge)), "开启传送门")
            if roll >= 5:
                engine.spawn_token("knowledge_check", label="传送门", role="marker", room_key=room_key)
                engine._log(f"邪教徒在{room.name}撕开了一道传送门！")
            else:
                engine._log("邪教徒试图撕开传送门，却什么也没发生。")
            return True
        return False

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """p75：蝙蝠受到物理伤害即死（不击晕）；邪教徒照常击晕。"""
        if getattr(monster, "template_id", "") != "bat":
            return False
        return attack_attr == "might"

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        flags = engine._haunt_flags()
        girl_room = self._girl_room(engine)
        result = []
        for action in actions:
            if action.id == "attack_girl":
                if flags.get("girl_dead") or int(flags.get("girl_stunned", 0)) > 0:
                    continue
                if girl_room is None or player.room_key != girl_room:
                    continue
            elif action.id == "close_portal":
                if not engine.tokens_in_room(player.room_key, "knowledge_check"):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "attack_girl":
            return self._attack_girl(engine, player)
        if action_id == "close_portal":
            return self._close_portal(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _attack_girl(self, engine: Any, player: Any) -> bool:
        """p146：力量或速度攻击命中 → 女孩卡上添一枚力量令牌。"""
        flags = engine._haunt_flags()
        if flags.get("girl_dead"):
            return False
        attack = engine._roll_attack(player, "might")
        defense = engine.roll_dice(self.GIRL_MIGHT, "女孩反抗")
        engine._log(f"{player.name} 扑向女孩：{attack} 对 {defense}。")
        if attack <= defense:
            engine._log("女孩躲开了这一击。")
            return True
        wounds = engine._advance_haunt_track("girl_wounds", 1)
        flags.setdefault("girl_pending", []).append(player.id)
        engine._log(f"女孩受了伤（{wounds}/5）。")
        if wounds >= 5:
            flags["girl_dead"] = True
            engine._set_winner("traitor", "女孩的血渗进地板——恶魔的契约兑现了。")
        return True

    def _close_portal(self, engine: Any, player: Any) -> bool:
        """p75：同房知识 4+ 关掉传送门。"""
        portal = next(iter(engine.tokens_in_room(player.room_key, "knowledge_check")), None)
        if portal is None:
            return False
        roll = engine._roll_attack(player, "knowledge")
        if roll < 4:
            engine._log(f"{player.name} 没能关上这道传送门（知识 {roll}）。")
            return True
        engine.remove_token(portal.uid)
        engine._log(f"{player.name} 念动咒语，传送门合上了。")
        return True

    # ------------------------------------------------------------- bot
    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        flags = engine._haunt_flags()
        if action_id == "attack_girl":
            if flags.get("girl_dead") or int(flags.get("girl_stunned", 0)) > 0:
                return True
            return False
        if action_id == "close_portal":
            # 关传送门要走过去，没门可关时别当目标
            return not bool(self._portals(engine))
        return False

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        flags = engine._haunt_flags()
        girl_room = self._girl_room(engine)
        if player.role == "traitor":
            if girl_room is None or flags.get("girl_dead"):
                return []
            return ["__room__" + girl_room]
        # 英雄：守住女孩；已经有传送门时优先去关掉
        portals = self._portals(engine)
        if portals:
            return ["__room__" + token.room_key for token in portals if token.room_key]
        if girl_room is None:
            return []
        return ["__room__" + girl_room]

    def bot_attack_blocked(self, engine: Any, player: Any, target: Any) -> bool:
        """p75/p146：英雄的胜线是**撑到计时轨走到 7**，打架换不来胜利。

        批次 13 实测（12 局）：英雄的死因基本是自己的送死攻击——空手对邪教徒
        打出「0 对 7」按 p20 吃满差值反击当场倒下，而邪教徒只是被击晕、下一回合
        照常回来干活。真人不会拿拳头去换一只会复活的邪教徒。只有手里有武器、
        或者力量本来就不吃亏时才还手。
        """
        if getattr(player, "role", None) != "hero":
            return False
        if getattr(target, "template_id", "") not in ("cultist", "bat"):
            return False
        might = int(getattr(player, "stats", {}).get("might", 0))
        weapons = engine.available_attack_weapons(player)
        return (not weapons) and might <= int(getattr(target, "might", 0))

    def bot_hazard_rooms(self, engine: Any, player: Any) -> set[str]:
        """p75：英雄的胜线是「活着撑满 7 个怪物回合」——本回合结束别留在怪物房里。

        真人守女孩时会贴着门口打游击，而不是站在邪教徒怀里过夜。本剧本英雄
        没有非留不可的房间（关门是顺手做的事），所以把所有未晕怪物所在房都
        标成"不该过夜"是安全的。
        """
        if getattr(player, "role", None) != "hero":
            return set()
        return {
            monster.room_key
            for monster in engine.state.monsters
            if getattr(monster, "room_key", "") and monster.stunned_turns <= 0
        }

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = []
        girl_room = self._girl_room(engine)
        room = engine.state.board.get(girl_room) if girl_room else None
        lines.append(f"女孩在{room.name if room else '未知房间'}")
        if flags.get("girl_dead"):
            lines.append("女孩已被献祭")
        else:
            lines.append(f"女孩伤势：{engine._haunt_track_value('girl_wounds')}/5")
        portals = self._portals(engine)
        if portals:
            lines.append(f"传送门：{len(portals)} 道")
        return lines

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        if engine._haunt_track_value("demon_timer") >= 7:
            if engine.state.winner is None:
                engine._set_winner("heroes", "恶魔失去了耐心——叛徒和他的仆从一起消失了。")
            return True
        if flags.get("girl_dead"):
            return True  # winner 已在献祭处设定
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄倒下了——没人再拦着邪教徒。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p75 的英雄胜 = 撑到计时 7
        # （恶魔收拾叛徒），叛徒提前死亡不等于英雄达成目标。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
