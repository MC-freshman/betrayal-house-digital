"""NightmareDreamMode（剧本 13）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


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

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """圣徽到手后，全体英雄去沉睡者的房间（p24 唤醒条件是"人在那间房"）。

        `wake_attempt` 没有 rooms 字段，静态表表达不了"沉睡者在哪"；没有这条
        时机器人只剩 key_rooms 保底，在门厅/庭院一带来回（seed137/3p、131/5p
        实测各 16 次、往返 21/28 步），英雄胜线几乎打不出来。圣徽还在地上时
        由 required_cards 的通用逻辑负责去捡，这里只管"送到沉睡者房间"。
        """
        if player.dead or player.role != "hero":
            return []
        sleeper_room = self._sleeper_room(engine)
        if not sleeper_room:
            return []
        symbol_held = any(
            other.role == "hero" and not other.dead and "omen_holy_symbol" in other.items
            for other in engine.state.players
        )
        if symbol_held:
            return [f"__room__{sleeper_room}"]
        return []

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """圣徽还压在预兆牌堆里时，英雄必须去翻新房间把它抽出来（p24/p95）。

        同 7/9 号：没有这条，机器人访到沉睡者房间也做不了检定（行动被
        "圣徽在房"闸门挡住），只能干等，英雄胜线永远开不了。
        """
        if player.dead or player.role != "hero":
            return False
        if any(
            "omen_holy_symbol" in other.items
            for other in engine.state.players
            if not other.dead
        ):
            return False
        if any(
            "omen_holy_symbol" in items for items in engine.state.room_items.values()
        ):
            return False
        return "omen_holy_symbol" in engine.state.card_decks.get("omen", [])

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
            if ok and engine.last_haunt_action_succeeded():
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
