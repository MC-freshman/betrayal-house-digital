"""BurningSandsMode（剧本 60）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


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
        # p71：三条线索分别在杂物间/游戏室/风琴房。缺任何一间，英雄的
        # "集齐三线索→解谜"胜利线就永远走不通（同 2 号五芒星室、3 号温室），
        # 开局按引擎能力把三间房拉进场。
        for template_id in self.CLUE_ROOMS.values():
            engine._ensure_room_in_play(template_id, room_key)
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
            return True  # p71：每回合只能尝试一条检定，失败也耗掉行动
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
        extra = 0
        if player.role != "traitor" and (
            self.BALL in getattr(player, "items", [])
            or self.BOARD in getattr(player, "items", [])
        ):
            extra = 1  # p71：水晶球/灵应板解谜多掷 1 骰
        if extra:
            player.stats["knowledge"] = int(player.stats.get("knowledge", 0)) + extra
        try:
            ok = engine._resolve_check(player, "knowledge", target, "解开谜语")
        finally:
            if extra:
                player.stats["knowledge"] = max(
                    0, int(player.stats.get("knowledge", 0)) - extra
                )
        if not ok:
            engine._log(f"{engine._player_label(player)} 把线索拼来拼去，始终差一点。")
            return True  # p71：每回合只能尝试一次解谜，失败也耗掉行动
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
    def _heroes_in(self, engine: Any, room_key: str) -> bool:
        return any(
            p.role == "hero" and not p.dead and p.room_key == room_key
            for p in engine.state.players
        )

    def _sphinx_may_enter(self, engine: Any, monster: Any, room_key: str) -> bool:
        """p142：不进有英雄的房间，除非叛徒或另一只斯芬克斯已在。"""
        if not self._heroes_in(engine, room_key):
            return True
        if any(
            p.role == "traitor" and not p.dead and p.room_key == room_key
            for p in engine.state.players
        ):
            return True
        return any(
            m.template_id == self.SPHINX
            and m.id != getattr(monster, "id", None)
            and m.room_key == room_key
            for m in engine.state.monsters
        )

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if getattr(monster, "template_id", "") != self.SPHINX:
            return False
        target = engine._find_monster_target(monster)
        if target is None or monster.room_key == target.room_key:
            return True
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) <= 1:
            return True
        steps = max(1, int(rolled))
        index = 0
        while index + 1 < len(path) and steps > 0:
            nxt = path[index + 1]
            if not self._sphinx_may_enter(engine, monster, nxt):
                break
            index += 1
            steps -= 1
        if index > 0:
            monster.room_key = path[index]
            room = engine.state.board.get(monster.room_key)
            engine._log(f"{monster.name} 移动到 {room.name if room else monster.room_key}。")
        return True

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
            # 已经拿到的、或永远掷不出 4+ 的线索不要再出现：失败返回 False
            # 不会消耗行动额度，机器人会在垃圾房空点 100+ 回合（批次 12 seed101/4p）。
            mine = self._clues(engine, player)
            if aid == "clue_junk" and (
                "might" in mine or not self._can_make_check(engine, player, "might", self.CLUE_TARGET)
            ):
                continue
            if aid == "clue_gameroom" and (
                "speed" in mine or not self._can_make_check(engine, player, "speed", self.CLUE_TARGET)
            ):
                continue
            if aid == "clue_organ" and (
                "sanity" in mine or not self._can_make_check(engine, player, "sanity", self.CLUE_TARGET)
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
    def _check_dice(self, engine: Any, player: Any, stat: str) -> int:
        """与引擎 _resolve_check 同一套骰数：属性 + 物品加成，夹在 1–8。"""
        try:
            dice = int(engine._effective_stat(player, stat)) + int(engine._check_bonus(player, stat))
        except Exception:
            dice = int((player.stats or {}).get(stat, 0) or 0)
        return max(1, min(8, dice))

    def _can_make_check(self, engine: Any, player: Any, stat: str, target: int) -> bool:
        """Betrayal 骰子面值 0/1/2，骰数 ×2 仍 < 目标就永远掷不出。"""
        return self._check_dice(engine, player, stat) * 2 >= int(target)

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """已拿到的、或骰数永远掷不出 4+ 的线索，不要再当目标/再点。"""
        mine = self._clues(engine, player)
        mapping = {
            "clue_junk": "might",
            "clue_gameroom": "speed",
            "clue_organ": "sanity",
        }
        if action_id in mapping:
            stat = mapping[action_id]
            if stat in mine:
                return True
            return not self._can_make_check(engine, player, stat, self.CLUE_TARGET)
        if action_id in ("solve_riddle", "traitor_solve_riddle"):
            if len(mine) < 3:
                return True
            need = self.HERO_SOLVE if action_id == "solve_riddle" else self.TRAITOR_SOLVE
            return not self._can_make_check(engine, player, "knowledge", need)
        return False

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        """线索没齐就做完一次换房间；集齐后若不在作祟房也要走。

        失败也耗行动之后，若还 leave=False，`_pending_haunt_action_here`
        会把人钉在垃圾房每回合空点力量 4+（批次 12 seed101/5p ×251）。
        """
        if player.dead:
            return False
        mine = self._clues(engine, player)
        if len(mine) >= 3:
            haunt_room = engine.state.meta["haunt_rule"].get("haunt_room")
            return player.room_key != haunt_room
        if not any(
            self._can_make_check(engine, player, stat, self.CLUE_TARGET)
            for stat in self.ROLL_TOKENS
            if stat not in mine
        ):
            # 剩下的线索永远掷不出：别被 leave 逼着在两间空房之间来回走。
            return False
        return True

    def bot_hazard_rooms(self, engine: Any, player: Any) -> set:
        """未晕的斯芬克斯房过夜会被拦死；正在找的线索房/作祟房除外。"""
        if getattr(player, "role", None) != "hero":
            return set()
        mine = self._clues(engine, player)
        leftover_hittable = any(
            self._can_make_check(engine, player, stat, self.CLUE_TARGET)
            for stat in self.ROLL_TOKENS
            if stat not in mine
        )
        # 解谜已经没戏时，斯芬克斯房不再是禁区——不去撞它们，对局就会空转到上限
        # （seed113/4p：最后一名英雄力量 1，在酒窖⇄积尘走廊踱了 205 圈）。
        if len(mine) < 3 and not leftover_hittable:
            return set()
        needed = {tid for stat, tid in self.CLUE_ROOMS.items() if stat not in mine}
        haunt_room = engine.state.meta.get("haunt_rule", {}).get("haunt_room")
        if len(mine) >= 3 and haunt_room:
            needed.add(engine.state.board[haunt_room].template_id if haunt_room in engine.state.board else "")
        hazards = set()
        for monster in engine.state.monsters:
            if monster.template_id != self.SPHINX or monster.stunned_turns > 0 or not monster.room_key:
                continue
            room = engine.state.board.get(monster.room_key)
            if room is not None and room.template_id in needed:
                continue
            hazards.add(monster.room_key)
        return hazards

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.dead or player.role not in ("hero", "traitor"):
            return []
        mine = self._clues(engine, player)
        haunt_room = engine.state.meta["haunt_rule"].get("haunt_room")
        if len(mine) >= 3:
            return [f"__room__{haunt_room}"] if haunt_room else []
        room = engine.state.board.get(player.room_key)
        current_tid = room.template_id if room is not None else None
        hittable: list[str] = []
        leftover: list[str] = []
        for stat in self.ROLL_TOKENS:
            if stat in mine:
                continue
            tid = self.CLUE_ROOMS[stat]
            leftover.append(tid)
            if self._can_make_check(engine, player, stat, self.CLUE_TARGET):
                hittable.append(tid)
        # 本房刚做过（失败也耗了行动）就换下一间，别被承诺机制拽回来。
        if current_tid in hittable and len(hittable) > 1:
            hittable = [tid for tid in hittable if tid != current_tid]
        if hittable:
            # 返回**模板 id**：bot 侧按 template_id 换算房间 key。
            return hittable
        if player.role == "traitor":
            # 自己掷不出剩下的线索，改去磨死英雄（解谜竞速已经没戏）。
            return [
                f"__room__{p.room_key}"
                for p in engine.state.players
                if p.role == "hero" and not p.dead and p.room_key
            ]
        # 英雄掷不出剩下的线索：解谜没戏。斯芬克斯不会进「只有英雄」的房间，
        # 不去撞它们，对局就会空转到上限。真人不会在酒窖踱 200 圈。
        return [
            f"__room__{monster.room_key}"
            for monster in engine.state.monsters
            if monster.template_id == self.SPHINX and monster.room_key
        ]

    def bot_goal_suppressed(self, engine: Any, player: Any) -> bool:
        """掷不出线索、场上又没有斯芬克斯时，空目标不能掉进 key_rooms 保底。"""
        if player.dead or player.role != "hero":
            return False
        mine = self._clues(engine, player)
        if len(mine) >= 3:
            return False
        if any(
            self._can_make_check(engine, player, stat, self.CLUE_TARGET)
            for stat in self.ROLL_TOKENS
            if stat not in mine
        ):
            return False
        return not any(m.template_id == self.SPHINX and m.room_key for m in engine.state.monsters)

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """解谜没戏且已经站在斯芬克斯房（或场上没怪）时，别再踱步。"""
        if player.dead or player.role != "hero":
            return False
        mine = self._clues(engine, player)
        if len(mine) >= 3:
            return False
        if any(
            self._can_make_check(engine, player, stat, self.CLUE_TARGET)
            for stat in self.ROLL_TOKENS
            if stat not in mine
        ):
            return False
        sphinxes = [m for m in engine.state.monsters if m.template_id == self.SPHINX and m.room_key]
        if not sphinxes:
            return True
        return any(m.room_key == player.room_key for m in sphinxes)

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = []
        for p in engine.state.players:
            mine = self._clues(engine, p)
            if p.role == "hero" and not p.dead:
                lines.append(f"{p.name}：线索 {len(mine)}/3（{','.join(mine) or '—'}）。")
        return lines
