"""SupernaturalAgingMode（剧本 44）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class SupernaturalAgingMode(GenericModeHandler):
    """剧本 44 死亡终将降临（Death Doth Find Us All）。

    权威原文：英雄手册 p55 / 叛徒手册 p126。

    · 衰老（p55）：每个英雄开局 1 枚衰老 token；叛徒回合开始，每个
      英雄掷 1 骰 → 加等量 token。每 token = 10 年。跨越十年界线时
      施加属性效果（p55 decade 表）。
    · 十年效果（简化为逐 token 应用；引擎无角色年龄字段）：
        token 1 (30s): +1 Sanity, +1 Knowledge
        token 2 (40s): -1 Speed, +1 Sanity
        token 3 (50s): -1 Might, -1 Knowledge
        token 4 (60s): -1 Might, -1 Speed, 1 mental damage
        token 5+ (70s+): -1 each trait
        校准（M10-54）：60s 行此前漏了 -1 Might（原文"-1 Might and -1 Speed,
        and take 1 point of mental damage"），只扣了速度。
    · 复活仪式（p55）：玩家数次成功检定。理智/知识 5+，在七类房间
      （地窖/焦房/地窖/画廊/厨房/五芒星室/塔楼）；每房一次。
    · 勋章（p55）：持有者衰老掷骰 -1（最低 0）；英雄死亡时持有者 +1 token。
    · 胜利：仪式完成 → 英雄胜；英雄全灭 → 叛徒胜。
    · 简化：叛徒吸食死亡力量（roll 3 dice add to traits）未建模；
      叛徒不可持勋章未在引擎层拦截。
    """

    mode = "supernatural_aging"

    RITUAL_ROOMS = ["catacombs", "charred_room", "crypt", "gallery", "kitchen", "pentagram_chamber", "tower"]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        aging = flags.setdefault("aging_tokens", {})
        for p in engine.state.players:
            if p.role == "hero" and not p.dead:
                aging[str(p.id)] = 1  # p55：开局每人 1 token
        engine._log("所有人的皮肤都在加速老化……")

    # ------------------------------------------------------------- 内部
    def _aging_tokens(self, engine: Any, player: Any) -> int:
        return int(engine._haunt_flags().get("aging_tokens", {}).get(str(getattr(player, "id", "")), 0))

    def _add_aging_tokens(self, engine: Any, player: Any, count: int) -> None:
        if count <= 0:
            return
        flags = engine._haunt_flags()
        aging = flags.setdefault("aging_tokens", {})
        pid = str(getattr(player, "id", ""))
        old_count = int(aging.get(pid, 0))
        new_count = old_count + count
        aging[pid] = new_count
        # 跨越十年界线：施加效果
        self._apply_decade_effects(engine, player, old_count, new_count)

    def _apply_decade_effects(self, engine: Any, player: Any, old: int, new: int) -> None:
        """p55 decade 表：跨越界线时施加效果（累计）。

        引擎没有角色年龄字段（角色卡上的起始年龄未建模），十年按 token 数
        折算：token 1 = 30s、2 = 40s、3 = 50s、4 = 60s、5+ = 70s+（开局那枚
        token 代表"刚跨入的这十年"，故从 30s 起算）。
        """
        effects = {
            1: [("sanity", 1), ("knowledge", 1)],              # 30s
            2: [("speed", -1), ("sanity", 1)],                  # 40s
            3: [("might", -1), ("knowledge", -1)],              # 50s：一项物理 + 一项精神
            4: [("might", -1), ("speed", -1)],                  # 60s（另加 1 点精神伤害）
        }
        for token_count in range(old + 1, new + 1):
            if token_count in effects:
                for stat, delta in effects[token_count]:
                    if delta > 0:
                        engine._increase_stat(player, stat, delta)
                    else:
                        engine._apply_stat_loss(player, stat, abs(delta))
            if token_count == 4:
                # 60s：1 mental damage
                engine._deal_damage(player, "mental", 1, source="衰老")
            if token_count >= 5:
                # 70s+：每个 token -1 each trait
                for stat in ("speed", "might", "sanity", "knowledge"):
                    engine._apply_stat_loss(player, stat, 1)
        engine._check_player_death(player)

    # ------------------------------------------------------------- 回合
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.role != "traitor" or player.dead:
            return
        # p55：每个英雄掷 1 骰衰老
        medallion_holder = next(
            (p for p in engine.state.players if p.role == "hero" and not p.dead
             and "omen_medallion" in p.items),
            None,
        )
        for hero in engine.state.players:
            if hero.role != "hero" or hero.dead:
                continue
            roll = engine.roll_dice(1, "衰老")
            if medallion_holder is not None and hero.id == medallion_holder.id:
                roll = max(0, roll - 1)  # p55：勋章 -1（最低 0）
            if roll > 0:
                self._add_aging_tokens(engine, hero, roll)
                engine._log(f"{hero.name} 衰老了 {roll} 个十年。")

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        used = set(engine._haunt_flags().get("ritual_rooms_used", []))
        for action in actions:
            if action.id == "ritual_roll":
                room_id = engine._current_room_template_id(player)
                if room_id not in self.RITUAL_ROOMS or room_id in used:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "ritual_roll":
            room_id = engine._current_room_template_id(player)
            used = set(engine._haunt_flags().get("ritual_rooms_used", []))
            if room_id not in self.RITUAL_ROOMS or room_id in used:
                engine._log("这个房间不能用于仪式（或已被使用）。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine.last_haunt_action_succeeded():
                used.add(room_id)
                engine._haunt_flags()["ritual_rooms_used"] = sorted(used)
                engine.spawn_token("knowledge_check", label="仪式成功", role="check", room_key=player.room_key)
            return ok
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 机器人
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p55：英雄胜 = 复活仪式满员——去还没用过的仪式房间。

        本类的规则数据里 `ritual_roll` **没有 `rooms` 字段**（房间白名单只在
        handler 的 available_actions/perform_action 里），机器人的通用目标
        换算因此算不出该去哪：实测 seed113/4p 在二楼平台来回 17 次、
        seed127/4p 在地下室楼梯来回 26 次，仪式进度 0、全员老死（M10-54）。
        """
        if player.dead or player.role != "hero":
            return []
        used = set(engine._haunt_flags().get("ritual_rooms_used", []))
        goals: list[str] = []
        for template_id in self.RITUAL_ROOMS:
            if template_id in used:
                continue
            key = next(
                (k for k, room in engine.state.board.items() if room.template_id == template_id),
                None,
            )
            if key:
                goals.append(f"__room__{key}")
        return goals

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """仪式房还没翻进场、牌堆还有牌时，先靠探索把它们翻出来。"""
        if player.dead or player.role != "hero":
            return False
        used = set(engine._haunt_flags().get("ritual_rooms_used", []))
        in_play = {room.template_id for room in engine.state.board.values()}
        missing = [
            template_id
            for template_id in self.RITUAL_ROOMS
            if template_id not in used and template_id not in in_play
        ]
        if not missing:
            return False
        return any(engine.has_remaining_room_cards(floor) for floor in (-1, 0, 1))

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p55：仪式成功次数 = 玩家数 → 英雄胜
        # 注意：本轨道的**声明名**必须与 action 的 "progress" 字段一致
        # （rule_data.setup.tracks 里写 ritual_progress，target=player_count）。
        # 旧版 tracks 写的是 "progress"、这里读 "ritual_progress"，而
        # engine._haunt_track_target(未声明轨道) 返回 0，于是 0 >= 0 恒真，
        # 作祟触发的第一个玩家回合就判英雄胜（实测 6/6 局）。
        if engine._haunt_track_value("ritual_progress") >= engine._haunt_track_target("ritual_progress"):
            engine._set_winner("heroes", "仪式完成了——超自然衰老停止了！")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "Death doth find us all——除了叛徒。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p55/p126 只认"仪式完成"，
        # 衰老由房子驱动，不随叛徒死亡停下。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
