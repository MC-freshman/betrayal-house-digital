"""BagOfTricksMode（剧本 62）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    HauntAction,
    _monster_id,
)


class BagOfTricksMode(GenericModeHandler):
    """剧本 62 魔袋把戏（Bag of Tricks）。

    权威原文：英雄手册 p73 / 叛徒手册 p144。

    机制（逐条对照原文）：
      · 开局（p73/p144）：叛徒角色**按规则从游戏中移除**（不是被打倒）——令牌
        离场，携带的物品/预兆留在原地、不弃掉（本仓库落到作祟房间地上，后来者
        走过去即可捡）。疯子令牌（红）放进作祟揭示的房间；回合/伤害轨归零。
      · 英雄胜线（p73）：与疯子**或与小玩意**同房时可做下面两种检定之一——
          ① 破解：知识 6+。骰数 = 英雄知识（持通灵板多掷 1 骰），上限 8；
             同房每有一件英雄携带的小玩意，**结果 +1**。成功把回合/伤害轨
             上调一格。
          ② 使用：理智检定。结果**低于回合/伤害轨当前格**时，在角色卡上放一枚
             理智检定令牌，并把轨道**下调一格**（持头骨少掷一骰，最少 1 骰）。
        同一英雄一回合不能两种都做（引擎"每回合一次剧本行动"即此约束）。
        理智检定令牌攒到「作祟时英雄数」→ 英雄获胜。
      · 疯子胜线（p144）：在带**物品符号**的房间做速度 4+ 搜索，成功在该房放
        一枚纪念品令牌；凑满 4 枚纪念品（或英雄全灭）→ 叛徒获胜。
      · 疯子不能做常规攻击（p144）：改在**与英雄同房时**每回合掷 4 骰使用一件
        随机小玩意。疯子被打中既不掉血也不昏迷，只会被英雄**摸走一件小玩意**
        （五边形令牌，等同普通物品可丢可交易可被抢）。
      · 疯子防守打赢时英雄不掉血，但该英雄的回合**立刻结束**（p144）。
      · 疯子免疫距离攻击（左轮的速度攻击由引擎 `immune_to` 拦在门外）；因为
        "挨打不掉血"这条已由 `on_monster_defeated` 接管，炸药同样伤不到他。

    已知简化：
      · 原文只写"取出若干三角/五边形令牌"、没写死枚数。本仓库让疯子袋中起手
        有 2 件小玩意，英雄靠打疯子摸走；小玩意以令牌形式挂在**英雄**身上
        （引擎的 `give_token` 只认玩家 id，疯子的存货记在 `flags["sack"]`，
        避免把怪物 id 塞进 token.holder 破坏存档）。
      · 随机小玩意 9 种结果（0-8）按可实现性取舍：0/1/2/6/8 只写日志（事件抽牌、
        物品重抽、指定点数、换房间板块、挪方形令牌都牵动引擎没有的子系统），
        3/4/5/7 真结算（移动、掉最高属性、换位、跳到目标房）。
      · "保险库可收两件（每回合一件）"未建模——本仓库的保险库没有物品符号，
        统一按"每个物品符号房间一件"处理；"不必先开保险库"原文本就允许。
      · 叛徒被移除时物品落在地上而非"搁在桌边"，英雄需要走过去捡（差别仅在
        多花移动力）。
    """

    mode = "bag_of_tricks"

    MADMAN = "madman"
    TRINKET = "trinket"
    SOUVENIR = "souvenir"
    SPIRIT_BOARD = "omen_spirit_board"
    SKULL = "omen_skull"
    SACK_START = 2
    TAP_TARGET = 6
    DICE_CAP = 8
    TRACK_MAX = 8
    SOUVENIR_NEEDED = 4
    # 轨道 ≥ 这一格时才值得赌理智检定（"roll < track"的胜率才压得过"再破解一次"）。
    # 它同时是行动出现门槛与 bot 门槛——两者必须同源，否则 UI/探针会看到
    # "行动出现但一局都没用过"的空转警告（批次13 实测 use_trinket 出现 3-6 次未用）。
    USE_TRINKET_MIN = 3

    # ------------------------------------------------------------- 工具
    def _madman(self, engine: Any) -> Any:
        return engine._monster_by_template(self.MADMAN)

    def _living_heroes(self, engine: Any) -> list[Any]:
        return [p for p in engine.state.players if p.role == "hero" and not p.dead]

    def _hero_count_at_start(self, engine: Any) -> int:
        flags = engine._haunt_flags()
        return max(1, int(flags.get("hero_count_at_start", len(self._living_heroes(engine)) or 1)))

    def _item_rooms(self, engine: Any) -> list[str]:
        """带物品符号的已放置房间（p144 的纪念品搜索点）。"""
        return [
            key
            for key, room in engine.state.board.items()
            if getattr(room, "symbol", None) == "item"
        ]

    def _trinkets_in_hand(self, engine: Any, player: Any) -> int:
        """同房间（含本人）英雄手上小玩意的总件数——知识检定结果加值用。"""
        total = 0
        for other in engine.state.players:
            if other.dead or other.room_key != player.room_key:
                continue
            total += len(engine.tokens_held_by(other.id, self.TRINKET))
        return total

    def _can_tap_here(self, engine: Any, player: Any) -> bool:
        """p73：与「小玩意」或「疯子」同房才能做检定。"""
        if engine.tokens_held_by(player.id, self.TRINKET):
            return True
        if self._trinkets_in_hand(engine, player) > 0:
            return True
        madman = self._madman(engine)
        return madman is not None and madman.room_key == player.room_key

    def _next_souvenir_room(self, engine: Any, madman: Any) -> str | None:
        done = set(engine._haunt_flags().get("souvenir_rooms", []))
        candidates = [key for key in self._item_rooms(engine) if key not in done]
        if not candidates:
            return None
        return min(candidates, key=lambda key: engine._path_length(madman.room_key, key))

    def _steal_trinket(self, engine: Any, madman: Any, hero: Any) -> None:
        """p73：英雄造成 ≥1 点物理伤害 → 不伤疯子，但可摸走一件小玩意。"""
        flags = engine._haunt_flags()
        if int(flags.get("sack", 0)) <= 0:
            engine._log(f"{madman.name} 的袋子已经空了。")
            return
        flags["sack"] = int(flags["sack"]) - 1
        engine.spawn_token(self.TRINKET, label="小玩意", role="carried", holder=hero.id)
        engine._log(
            f"{hero.name} 抓住破绽，从{madman.name}的袋子里摸走一件小玩意"
            f"（袋中还剩 {flags['sack']} 件）。"
        )

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["traitor_removed"] = True
        flags["sack"] = self.SACK_START
        flags["souvenir_rooms"] = []
        flags["hero_count_at_start"] = max(1, len(self._living_heroes(engine)))
        engine._set_haunt_track_value("trinket_progress", 0)
        engine._set_haunt_track_value("trinket_tokens", 0)
        engine._set_haunt_track_value("souvenir_count", 0)
        # p73：理智检定令牌的目标 = 作祟时英雄数（按人数动态钉进轨道，UI 才显示对）。
        engine._haunt_tracks().setdefault("trinket_tokens", {})["target"] = int(
            flags["hero_count_at_start"]
        )
        engine._haunt_tracks().setdefault("trinket_progress", {})["target"] = self.TRACK_MAX

        # p73/p144：叛徒角色从游戏中移除——令牌离场，携带物落地不弃掉。
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine._drop_inventory_on_death(traitor)
            traitor.dead = True
            engine._log(f"{traitor.name} 消失在空气中——TA 离开了游戏。")

        madman = self._madman(engine)
        if madman is None:
            # 兜底：rule_data 的 spawn=haunt_room 正常情况下已由引擎生成。
            spec = next(
                (
                    s
                    for s in ((haunt.rule_data or {}).get("monsters", []))
                    if s.get("template_id") == self.MADMAN
                ),
                {"template_id": self.MADMAN},
            )
            madman = engine._spawn_single_haunt_monster(dict(spec), room_key)
        if madman is not None:
            engine._log("疯子从虚空中走来，肩上扛着一只鼓鼓囊囊的袋子。")
        engine.check_victory()

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        if player.role != "hero" or not self._can_tap_here(engine, player):
            return []
        if int(engine._haunt_track_value("trinket_tokens")) >= self._hero_count_at_start(engine):
            return []
        track = engine._haunt_track_value("trinket_progress")
        result = []
        for spec in engine._generic_haunt_actions():
            action_id = str(spec.get("id", ""))
            if action_id not in {"tap_trinkets", "use_trinket"}:
                continue
            # 轨道太低时"roll < 0/1/2"几乎不可能命中：不给这次检定白掷。
            if action_id == "use_trinket" and track < self.USE_TRINKET_MIN:
                continue
            result.append(
                HauntAction(
                    action_id,
                    str(spec.get("label", action_id)),
                    str(spec.get("detail", "")),
                    dict(spec.get("data", {})),
                )
            )
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id not in {"tap_trinkets", "use_trinket"}:
            return super().perform_action(engine, player, action_id, data)
        if player.role != "hero" or not self._can_tap_here(engine, player):
            return False
        if action_id == "tap_trinkets":
            self._tap(engine, player)
        else:
            if engine._haunt_track_value("trinket_progress") < self.USE_TRINKET_MIN:
                return False
            self._use_trinket(engine, player)
        return True

    def _tap(self, engine: Any, player: Any) -> None:
        """p73：知识 6+（通灵板 +1 骰，同房每件小玩意结果 +1）→ 轨道 +1。"""
        dice = engine._effective_stat(player, "knowledge")
        has_board = engine._has_item(player, self.SPIRIT_BOARD)
        if has_board:
            dice += 1
        dice = max(1, min(self.DICE_CAP, dice))
        roll = engine.roll_dice(dice, "破解小玩意")
        if has_board:
            engine._log(f"{player.name} 借着通灵板与灵界搭话（知识 {dice} 骰）。")
        bonus = self._trinkets_in_hand(engine, player)
        total = roll + bonus
        if bonus:
            engine._log(f"同房英雄手上的 {bonus} 件小玩意让线索更清晰（{roll}+{bonus}={total}）。")
        if total < self.TAP_TARGET:
            engine._log(f"{player.name} 没能破解小玩意的用法（{total}，需要 {self.TAP_TARGET}）。")
            return
        value = engine._advance_haunt_track("trinket_progress", 1)
        engine._log(f"{player.name} 摸清了小玩意的一点门道：回合/伤害轨升到 {value}。")

    def _use_trinket(self, engine: Any, player: Any) -> None:
        """p73：理智检定；结果 < 轨道当前格 → 得一枚理智检定令牌，轨道 -1。"""
        track = engine._haunt_track_value("trinket_progress")
        dice = engine._effective_stat(player, "sanity")
        has_skull = engine._has_item(player, self.SKULL)
        if has_skull:
            dice -= 1
        dice = max(1, min(self.DICE_CAP, dice))
        roll = engine.roll_dice(dice, "使用小玩意")
        if has_skull:
            engine._log(f"{player.name} 攥着冰冷的头骨，手有点抖（理智 {dice} 骰）。")
        if roll >= track:
            engine._log(f"{player.name} 没敢按下小玩意的机关（理智 {roll} 对轨道 {track}）。")
            return
        need = self._hero_count_at_start(engine)
        tokens = engine._advance_haunt_track("trinket_tokens", 1)
        engine._set_haunt_track_value("trinket_progress", track - 1)
        engine._log(
            f"{player.name} 用小玩意撬开了虚空的一角（理智 {roll} < 轨道 {track}）："
            f"理智检定令牌 {tokens}/{need}。"
        )
        if tokens >= need:
            engine._set_winner("heroes", "小玩意的力量被彻底破解——疯子被送走了。")

    # ------------------------------------------------------------- 疯子回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """p144：疯子的一整个回合由剧本接管（搜刮 → 移动 → 用小玩意）。"""
        if _monster_id(monster) != self.MADMAN:
            return False
        self._madman_turn(engine, monster)
        return True

    def _madman_turn(self, engine: Any, monster: Any) -> None:
        self._collect_souvenir(engine, monster)
        if engine.state.winner:
            return
        dest = self._next_souvenir_room(engine, monster)
        if dest and dest != monster.room_key:
            path = engine._shortest_path(monster.room_key, dest)
            if len(path) > 1:
                steps = max(1, engine.roll_dice(monster.speed, "疯子移动"))
                monster.room_key = path[min(len(path) - 1, steps)]
                room = engine.state.board.get(monster.room_key)
                engine._log(f"{monster.name} 逛到{room.name if room else '未知房间'}翻找纪念品。")
        if any(
            p.role == "hero" and not p.dead and p.room_key == monster.room_key
            for p in engine.state.players
        ):
            self._use_random_trinket(engine, monster)

    def _collect_souvenir(self, engine: Any, monster: Any) -> bool:
        """p144：物品符号房间做速度 4+ → 该房放一枚纪念品；满 4 枚 → 叛徒胜。"""
        room = engine.state.board.get(monster.room_key)
        if room is None or getattr(room, "symbol", None) != "item":
            return False
        flags = engine._haunt_flags()
        collected = flags.setdefault("souvenir_rooms", [])
        if monster.room_key in collected:
            return False
        roll = engine.roll_dice(monster.speed, "搜索纪念品")
        if roll < 4:
            engine._log(f"{monster.name} 在{room.name}翻了半天，什么也没找到（速度 {roll}）。")
            return False
        collected.append(monster.room_key)
        count = engine._advance_haunt_track("souvenir_count", 1)
        engine.spawn_token(self.SOUVENIR, label="纪念品", role="marker", room_key=monster.room_key)
        engine._log(
            f"{monster.name} 从{room.name}收走了一件纪念品（{count}/{self.SOUVENIR_NEEDED}）。"
        )
        if count >= self.SOUVENIR_NEEDED:
            engine._set_winner("traitor", "疯子集齐了四件纪念品——他转身走向门口。")
        return True

    def _use_random_trinket(self, engine: Any, monster: Any) -> None:
        """p144：代替普通攻击，掷 4 骰用一件随机小玩意（0-8 号效果）。"""
        roll = engine.roll_dice(4, "小玩意")
        engine._log(f"{monster.name} 从袋子里掏出一件小玩意，掷出了 {roll}。")
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if roll == 0:
            engine._log("小玩意炸出一团彩纸：每个英雄都被迫分心了一瞬（未建模：抽事件卡）。")
            return
        if roll == 1:
            engine._log('小玩意"噗"地吐出烟雾，屋里的东西全乱了套（未建模：物品重抽）。')
            return
        if roll == 2:
            engine._log(f"{monster.name} 把小玩意捏在手心——下一掷由它说了算（未建模）。")
            return
        if roll == 3:
            self._madman_free_step(engine, monster)
            return
        if roll == 4:
            self._trinket_trait_shock(engine, heroes)
            return
        if roll == 5:
            self._trinket_swap(engine, monster, heroes)
            return
        if roll == 6:
            engine._log("小玩意咯咯作响，房间的轮廓晃了一下又复位（未建模：换房间板块）。")
            return
        if roll == 7:
            dest = self._next_souvenir_room(engine, monster)
            if dest and dest != monster.room_key:
                monster.room_key = dest
                room = engine.state.board.get(dest)
                engine._log(f"{monster.name} 一步跨进了{room.name if room else '未知房间'}。")
            else:
                engine._log(f"{monster.name} 在屋里转了一圈，没找到想去的地方。")
            return
        engine._log("小玩意从疯子指缝里滑走了，什么也没发生（未建模）。")

    def _madman_free_step(self, engine: Any, monster: Any) -> None:
        """p144 · 3：把疯子推进相邻的一个房间（不必有门相连）。"""
        dest = self._next_souvenir_room(engine, monster)
        if dest is None:
            return
        path = engine._shortest_path(monster.room_key, dest)
        if len(path) > 1:
            monster.room_key = path[1]
            room = engine.state.board.get(monster.room_key)
            engine._log(f"{monster.name} 被小玩意拽进了{room.name if room else '未知房间'}。")

    def _trinket_trait_shock(self, engine: Any, heroes: list[Any]) -> None:
        """p144 · 4：每个英雄掷 1 骰，从最高属性上扣掉这么多点。"""
        for hero in heroes:
            amount = engine.roll_damage_dice(1, "小玩意反噬")
            if amount <= 0:
                continue
            stat = max(
                ("speed", "might", "sanity", "knowledge"),
                key=lambda name: engine._effective_stat(hero, name),
            )
            names = {"speed": "速度", "might": "力量", "sanity": "理智", "knowledge": "知识"}
            engine._apply_stat_loss(hero, stat, amount)
            engine._log(f"{hero.name} 的最高属性（{names[stat]}）被打掉了 {amount} 点。")
            engine._check_player_death(hero)

    def _trinket_swap(self, engine: Any, monster: Any, heroes: list[Any]) -> None:
        """p144 · 5：与同层最近的英雄换位；本层没英雄就把最近的英雄拽过来。"""
        here = engine.state.board.get(monster.room_key)
        same_floor = [
            p
            for p in heroes
            if engine.state.board.get(p.room_key) is not None
            and here is not None
            and engine.state.board[p.room_key].floor == here.floor
        ]
        if same_floor:
            target = min(same_floor, key=lambda p: engine._path_length(monster.room_key, p.room_key))
            monster.room_key, target.room_key = target.room_key, monster.room_key
            engine._log(f"一阵眩晕过后，{monster.name} 和{target.name} 互换了位置。")
            return
        if not heroes:
            return
        target = min(heroes, key=lambda p: engine._path_length(monster.room_key, p.room_key))
        engine._log(f"{monster.name} 把{target.name} 硬生生拽到了自己面前。")
        target.room_key = monster.room_key

    # ------------------------------------------------------------- 战斗
    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p73/p144：打中疯子不造成伤害、也不昏迷——他只是被掏了口袋。"""
        if _monster_id(monster) != self.MADMAN:
            return False
        engine._log(f"{monster.name} 挨了一下，却像没事人一样站住了。")
        return True

    def monster_counterattack_disabled(self, engine: Any, monster: Any) -> bool:
        """p144：疯子防守打赢时不造成伤害（只让英雄的回合立刻结束）。"""
        return _monster_id(monster) == self.MADMAN

    def on_attack_resolved(
        self, engine: Any, attacker: Any, target: Any, attacker_wins: bool
    ) -> None:
        if _monster_id(target) != self.MADMAN:
            return
        if getattr(attacker, "role", None) != "hero":
            return
        if not attacker_wins:
            # p144：疯子防守得手 → 英雄不掉血，但回合立刻结束。
            attacker.movement_stopped = True
            attacker.steps_remaining = 0
            engine._log(f"{attacker.name} 被{target.name} 缠住，回合就此结束。")
            return
        # 攻击的代价（自伤武器）可能先要了英雄的命——死人拿不动小玩意。
        if getattr(attacker, "dead", False):
            return
        # p73：造成 ≥1 点物理伤害 → 不伤疯子，但可摸走一件小玩意。
        if getattr(engine, "_last_attack_attr", "") in ("might", "speed"):
            self._steal_trinket(engine, target, attacker)

    # ------------------------------------------------------------- bot
    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """机器人策略：轨道够高就"用"（理智检定），不够高就"破解"先抬轨。"""
        if action_id == "tap_trinkets":
            return engine._haunt_track_value("trinket_progress") >= self.USE_TRINKET_MIN
        if action_id == "use_trinket":
            return engine._haunt_track_value("trinket_progress") < self.USE_TRINKET_MIN
        return False

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """手里有小玩意的英雄在哪都能破解——没必要追着疯子满屋子跑。"""
        if player.role != "hero":
            return False
        return bool(engine.tokens_held_by(player.id, self.TRINKET))

    def bot_attack_blocked(self, engine: Any, player: Any, target: Any) -> bool:
        """疯子袋里没小玩意了就别再捶他：打不掉血，只是白费一次攻击。"""
        if _monster_id(target) != self.MADMAN:
            return False
        if player.role != "hero":
            return True
        return int(engine._haunt_flags().get("sack", 0)) <= 0

    def bot_weapon_bonus(self, engine: Any, player: Any, target: Any, weapon_id: str | None) -> int:
        """p73：摸疯子只换一件小玩意、**不造成任何伤害**——体力见底时别拿自伤
        武器（献祭匕首/血匕首，攻击 +4 但要自伤 1）去换。

        批次13 实测：seed137/3p 两名英雄都死在献祭匕首的 1 点自伤上，一件小玩意
        都没摸到，疯子一路搜满四件纪念品。体力还厚时这笔交换是划算的（+4 攻击
        更容易赢下抢袋子的对决），所以只在"速度+力量 ≤ 4"时才重罚。
        """
        if _monster_id(target) != self.MADMAN or not weapon_id:
            return 0
        weapon = engine.catalog.cards.get(weapon_id)
        if weapon is None or int(weapon.data.get("self_damage", 0)) <= 0:
            return 0
        stamina = int(engine._effective_stat(player, "speed")) + int(
            engine._effective_stat(player, "might")
        )
        return -60 if stamina <= 4 else 0

    # ------------------------------------------------------------- UI
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        need = self._hero_count_at_start(engine)
        tokens = int(engine._haunt_track_value("trinket_tokens"))
        track = engine._haunt_track_value("trinket_progress")
        lines = [f"理智检定令牌：{tokens}/{need}（回合/伤害轨 {track}/{self.TRACK_MAX}）"]
        collected = len(engine._haunt_flags().get("souvenir_rooms", []))
        lines.append(f"疯子已收集纪念品：{collected}/{self.SOUVENIR_NEEDED}")
        lines.append(f"疯子袋中的小玩意：{int(engine._haunt_flags().get('sack', 0))} 件")
        holders = [
            p.name for p in engine.state.players if engine.tokens_held_by(p.id, self.TRINKET)
        ]
        if holders:
            lines.append("英雄手中的小玩意：" + "、".join(holders))
        return lines

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        need = self._hero_count_at_start(engine)
        if int(engine._haunt_track_value("trinket_tokens")) >= need:
            engine._set_winner("heroes", "小玩意的力量被彻底破解——疯子被送走了。")
            return True
        if int(engine._haunt_track_value("souvenir_count")) >= self.SOUVENIR_NEEDED:
            engine._set_winner("traitor", "疯子集齐了四件纪念品——他转身走向门口。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也消失了。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p73 里叛徒角色是**按规则从游戏中移除**的，
        # 不是被英雄打倒的，所以它"死亡"绝不代表英雄达成目标。旧实现 return False
        # 会让兜底在作祟触发的第一个玩家回合就判英雄胜（实测 6/6 局触发即结束）。
        return True
