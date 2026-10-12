"""WebEscapeMode（剧本 4）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


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

    # ------------------------------------------------------------- bot 目标
    bot_goal_exclusive = True

    # B 类小修（2026-10-06，handoff §11.33 ① 的第一本样板）：attack_web /
    # destroy_eggs_* 的 requires 是 same_room:web / same_room:revealer，没有
    # rooms 字段，通用目标换算只能看见 open_front_door 的前门——而前门在
    # 网破卵毁之前做不成，英雄 bot 便集体涌向前门或在空屋打转，毁卵行动
    # offered 高而 used 近零。照 47/68 号的动态目标口径补：
    # 先去被困者的房间撕网毁卵，前门交给静态表（open_front_door.rooms）。
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role == "traitor":
            return []
        flags = engine._haunt_flags()
        if flags.get("web_destroyed") and flags.get("eggs_destroyed"):
            return ["entrance_hall"]
        if flags.get("web_destroyed") and not flags.get("eggs_destroyed"):
            medicine = {"item_medical_kit", "item_healing_salve"}
            if not medicine.intersection(player.items):
                loose = ["__room__" + key for key, cards in engine.state.room_items.items()
                         if medicine.intersection(cards)]
                if loose:
                    return loose
        if not flags.get("web_destroyed") or not flags.get("eggs_destroyed"):
            trapped_id = flags.get("trapped_id")
            trapped = next(
                (p for p in engine.state.players if p.id == trapped_id and not p.dead),
                None,
            )
            if trapped is not None:
                return ["__room__" + trapped.room_key]
            web = next(iter(engine.tokens_of_kind("web")), None)
            if web is not None and getattr(web, "room_key", None):
                return ["__room__" + web.room_key]
        return []

    def bot_preserve_item(self, engine, player, card_id):
        return (player.role == "hero" and not engine._haunt_flags().get("eggs_destroyed")
                and card_id in ("item_medical_kit", "item_healing_salve"))

    def bot_action_priority(self, engine, player, action_id):
        return {"destroy_eggs_salve": 100, "destroy_eggs_medical_kit": 90}.get(action_id, 0)

    def bot_attack_blocked(self, engine, player, target):
        # 撕网/毁卵/出门才推进胜利，普通攻击蜘蛛既不减倒计时也不解救被困者。
        return player.role == "hero" and _monster_id(target) == "giant_spider"

    def _web_weapon(self, engine, player):
        weapons = [c for c in engine.available_attack_weapons(player)
                   if c not in ("item_revolver", "omen_ring", "item_dynamite")]
        return max(weapons, key=lambda c: engine._attack_bonus_from_inventory(player, c), default=None)

    def action_item_cards(self, engine, player, action_id):
        weapon = self._web_weapon(engine, player) if action_id == "attack_web" else None
        return [weapon] if weapon else []

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """网已破、卵还没毁、全队没人带医疗物品时：去翻新房间找医疗箱/药膏。

        物品只可能从新房间的物品堆里翻出来；此时守在被困者身边干等不是
        人的打法（9 号圣徽同款问题）。网还没撕时不触发——先救人要紧。
        """
        if player.role == "traitor":
            return False
        flags = engine._haunt_flags()
        if flags.get("eggs_destroyed") is True:
            return False
        for p in engine.state.players:
            if p.role != "traitor" and not p.dead:
                if "item_medical_kit" in p.items or "item_healing_salve" in p.items:
                    return False
        mobile = [p for p in engine.state.players if p.role == "hero" and not p.dead
                  and p.id != flags.get("trapped_id")]
        runner = min(mobile, key=lambda p: (p.stats.get("might", 0), p.id), default=None)
        return runner is not None and runner.id == player.id

    def bot_action_blocked(self, engine, player, action_id):
        return action_id == "attack_web" and self.bot_wants_explore(engine, player)

    def bot_leave_after_action(self, engine, player):
        return self.bot_wants_explore(engine, player)

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
            if action.id == "attack_web" and player.attack_used:
                continue
            # 蛛网已破就别再显示"攻击蛛网"
            if action.id == "attack_web" and flags.get("web_destroyed"):
                continue
            # 卵已毁就别再显示销毁卵
            if action.id in {"destroy_eggs_medical_kit", "destroy_eggs_salve"} and flags.get("eggs_destroyed"):
                continue
            if action.id in {"destroy_eggs_medical_kit", "destroy_eggs_salve"}:
                card = "item_healing_salve" if action.id.endswith("salve") else "item_medical_kit"
                if not engine.item_action_available(card):
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
            if flags.get("web_destroyed") or player.attack_used:
                return False
            if not any(a.id == action_id for a in super().available_actions(engine, player)):
                return False
            weapon = self._web_weapon(engine, player)
            bonus = engine._attack_bonus_from_inventory(player, weapon)
            attack = engine._roll_attack(player, "might", bonus)
            defense = engine.roll_dice(4, "蛛网防御")
            engine._last_haunt_action_success = attack > defense
            player.attack_used = True
            if weapon:
                engine._mark_item_action(weapon, "use")
            if attack > defense:
                engine._advance_haunt_track("web_damage", 1)
            engine._log(f"{player.name} 攻击蛛网：{attack} 对 {defense}。")
            ok = True
            if engine.last_haunt_action_succeeded() and engine._haunt_track_value("web_damage") >= engine._haunt_track_target("web_damage"):
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
            card = "item_healing_salve" if action_id.endswith("salve") else "item_medical_kit"
            if not engine.item_action_available(card):
                return False
            # 治疗药膏免检定（p15 "without a Knowledge roll"）
            if action_id == "destroy_eggs_salve":
                engine._mark_item_action(card, "use")
                for card_id in ("item_healing_salve",):
                    if card_id in player.items:
                        engine._discard_card_from_player(player, card_id, return_to_room=False)
                flags["eggs_destroyed"] = True
                engine._log(f"{player.name} 用治疗药膏销毁了蛛卵。")
                engine.check_victory()
                return True
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                engine._mark_item_action(card, "use")
            if engine.last_haunt_action_succeeded():
                flags["eggs_destroyed"] = True
            return ok

        if action_id == "open_front_door":
            ok = super().perform_action(engine, player, action_id, data)
            if engine.last_haunt_action_succeeded():
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
