"""LabyrinthEscapeMode（剧本 68）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


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
      理智检定令牌放到该英雄身上。叛徒可以在她回合内的任何时候逼她白走一格
      （不花移动点）；回合结束迷乱解除。
    · 钥匙禁令（p150）：叛徒既不能拾取也不能抢夺钥匙——`grab_key` 只挂在
      side=heroes 上，令牌也不走引擎的卡牌抢夺分支，所以这条由结构保证。
    · 胜负（p79/p150）：英雄胜 = 逃出人数 ≥「作祟开始时活着的英雄数的一半」；
      叛徒胜 = 迷宫合拢，或死亡英雄超过一半。叛徒死亡**不**判英雄胜：门不会
      因为死人而打开，迷宫也照样合得拢（引擎通用兜底在此吸收）。

    已知简化：
        · 房间重排按**连通优先**实现（`engine._rearrange_floor`）：每层保留起始牌
          作锚点，其余板块经"门兼容边"走成一棵生成树，硬约束"同层全连通"由构造
          保证；原文的"任意配置"取该构造给出的那一种（不是唯一解，也不是让
          玩家自选布局的交互界面）。地下墓穴现在是**真删除**
          （`engine._detach_room`），不再是塌方标记近似；里面的人与怪先搬到邻接
          房间、不走坠亡结算。
        · 「可把方形令牌挪到同层任意合法位置」未建模：本仓库的钥匙/仆人是重排
          **之后**才布点的（见下条），没有"先存在的方形令牌"需要挪；其余令牌
          按原版随所在板块一起移动（`_relocate_room` 已实现）。
        · "万能钥匙可替代一把钥匙"未实现：本项目 80 张卡牌目录里没有骷髅钥匙
          （见 67 号同款说明），要落地得先扩卡池并同步后端的数量断言。
        · 迷乱者的那一格位移固定在"她的回合结束"执行（原文是"回合内任何时刻"），
          且特殊移动所需的属性检定不免判（本引擎的特殊移动选项本就无需检定）。
        · 平衡观察（2026-09-16，11 种子 × 3/4/5 人 = 33 局 bot 对局）：叛徒胜 32 /
          英雄胜 1（seed151/4p 逃出 2 人）。这个比例是**规则本身**决定的，不是
          bot 漏做：轨第 n 格掷 n 枚 0/1/2 骰求 ≥6，第 3 格起才有胜算（3 枚全 2 =
          1/27），到第 5 格累计过 5 成、第 6~8 格必合拢——即英雄通常只有 5~8 个
          回合；其间仆人还会用理智把持钥匙的英雄打成迷乱，叛徒每回合把这格
          钥匙的持有者从入口大厅推出去。两条胜线都真实可达（英雄胜那一局
          flee_labyrinth×2 + unlock_door×3 + grab_key×3 全部走通），属"难而非坏"。
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
        # p150：Rearrange the remaining room tiles in the House into any
        # configuration you like, keeping all rooms on the same floors and
        # ensuring that all the rooms on a floor are connected together by valid
        # movement routes. —— 逐层重排；连通性由 engine._rearrange_floor 的
        # 贪心构造保证（锚点留给该层起始牌，其余经门兼容边走成一棵生成树）。
        moved = sum(engine._rearrange_floor(floor) for floor in (-1, 0, 1))
        if moved:
            engine._log(f"石墙彼此碾过：{moved} 块房间被挪到了新位置，迷宫重新咬合。")
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
        """p150：Remove the Catacombs from the House and set it aside; it will no
        longer be used. —— 真删（`_detach_room`），不再用塌方标记近似。

        里面的人与怪先搬到邻接的已探索房间（不走坠亡结算），板块随即摘除。
        """
        key = next(
            (k for k, room in sorted(engine.state.board.items()) if room.template_id == self.CATACOMBS),
            "",
        )
        if not key:
            return
        refuge = self._catacomb_refuge(engine, key)
        if not refuge:
            engine._log("地下墓穴无处可撤（它被孤立在别处）：本局仍按原样使用它（已知简化）。")
            return
        engine._evict_room(key, refuge)
        engine._detach_room(key, return_to_deck=False, force=True)
        engine._log("地下墓穴被整个从房子里摘了出去——它再也不会出现了。")

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
            engine.spawn_token(self.CONFUSED, label="理智检定", role="check", holder=target.id)
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

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """拿着钥匙站进大厅就别再主动走出去。

        p79 的开门条件是"所有钥匙都在**入口大厅里**英雄的手上"，而
        `bot_goal_rooms` 在"人已经站在目标房间"时返回空集（`_next_steps_toward`
        会跳过当前房间），寻路失去牵引；没有这道闸门，机器人会跟着通用目标
        （保护揭示者一类）或空转漂出门外，把进度条自己清零。

        注意：实测（seed3/4p 基线 33 局）里把持钥匙英雄**拖出**大厅的并不是
        他自愿走动，而是 p150 的迷乱强制位移——仆人用理智打赢后，叛徒在英雄
        回合结束时逼她白走一格，`_stumble_option` 的机器人分支专挑"离前门越远
        越好"。所以这道闸门并不改变那批对局的结局（迷乱照旧生效），它只是堵住
        "自愿走出去"这一条独立漏洞。

        只有在"地面上还剩钥匙、且没有别的空手队友能去捡"时才离厅——那时
        他不去就没人去了（队友阵亡后钥匙会落回房间）。
        """
        if player.role != "hero" or player.dead:
            return False
        if not self._in_hall(engine, player):
            return False
        flags = engine._haunt_flags()
        if flags.get("door_unlocked"):
            # 门已开：留在厅里（本回合移动点不够就下回合再花 2 点逃）
            return True
        if not engine.tokens_held_by(player.id, self.KEY):
            return False  # 空手：该出去找钥匙，不该在厅里耗着
        floor_keys = [token for token in engine.tokens_of_kind(self.KEY) if token.room_key]
        if not floor_keys:
            return True  # 钥匙都在人手上，等他们走过来
        keyless_others = [
            other for other in engine.state.players
            if other.role == "hero" and not other.dead and other.id != player.id
            and not engine.tokens_held_by(other.id, self.KEY)
        ]
        return len(floor_keys) <= len(keyless_others)

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
