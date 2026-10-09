"""AlienAbductionMode（剧本 6）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


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
