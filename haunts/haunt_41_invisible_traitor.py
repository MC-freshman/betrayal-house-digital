"""InvisibleTraitorMode（剧本 41）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class InvisibleTraitorMode(GenericModeHandler):
    """剧本 41 隐形叛徒（Invisible Traitor）。

    权威原文：英雄手册 p52 / 叛徒手册 p123。

    · 隐形：叛徒不可见。sneak attack = 掷 ceil(原始英雄数/2) 骰的
      物理伤害，无防御（p123 "Your opponent can't defend against this"）。
    · 侦测：被偷袭幸存后知识 3+ 探知叛徒所在房间（detect_traitor 行动）。
    · 胜利：叛徒死亡 → 英雄胜（handler 显式接管，不再依赖引擎通用兜底）。
    · 机器人（M10-56 修）：`detect_traitor` 此前**没有任何效果**、`detections`
      轨道也永远不动（动作缺 `progress` 字段）——五名英雄每回合都去侦测、却
      既不推进也不追击，而英雄画像默认 `attack_traitor_players: False`，唯一的
      胜线"叛徒死"在 AI 层断开：seed109/6p 实测 300 回合收不了场（侦测 217 次）。
      现在侦测成功会把叛徒所在房间写进 `detected_room` 并推进轨道，英雄也会
      循着线索奔向叛徒（见 bot_goal_rooms），画像放开攻击叛徒。
    · 偷袭落地（M10-56）：`defense_roll_disabled` 让叛徒**持物品以外**的攻击
      按"对手无法防御"结算（引擎把防守骰按 0 计，新增的同名钩子默认关，
      其它剧本行为不变）。此前完全走普通对抗，叛徒的隐形优势等于不存在
      （英雄 15/3 一边倒）。
    · 简化：偷袭伤害仍走引擎 PvP 公式（攻击骰 − 0），不是原文的
      "掷 ceil(原始英雄数/2) 枚骰"；骷髅/灵应板追踪/偷窃未建模。
    """

    mode = "invisible_traitor"

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("detected_by", [])
        flags.setdefault("detected_room", None)
        engine._log("叛徒的身影从视野中消失了——TA 已经隐形。")

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        return False  # 无怪物

    # ------------------------------------------------------------- 内部
    def _traitor(self, engine: Any) -> Any | None:
        return next(
            (p for p in engine.state.players if p.role == "traitor" and not p.dead), None
        )

    def defense_roll_disabled(self, engine: Any, attacker: Any, target: Any, weapon_card_id: str | None = None) -> bool:
        """p123：叛徒的非物品攻击都是偷袭——"Your opponent can't defend against this"。

        持物品的攻击按普通攻击结算（原文 "Unless you are attacking with an
        item"）。已知偏差：伤害走引擎的 PvP 公式（攻击骰 − 0），而不是原文的
        "掷 ceil(原始英雄数/2) 枚骰"——引擎的玩家对玩家伤害没有加值钩子；
        "对手无法防御"这一半已经落地（M10-56）。
        """
        if getattr(attacker, "role", None) != "traitor":
            return False
        if getattr(target, "role", None) != "hero":
            return False
        return not weapon_card_id

    # ------------------------------------------------------------- 行动
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        """p52：侦测成功 → 探知叛徒所在房间。

        这条行动过去是纯空转：规则数据里既没有 `set_flags` 也没有 `progress`，
        通用行动管线跑完只写一句日志——轨道不动、位置不知、机器人也拿不到
        任何可追的线索（M10-56 修，见类 docstring）。
        """
        if action_id != "detect_traitor":
            return super().perform_action(engine, player, action_id, data)
        ok = super().perform_action(engine, player, action_id, data)
        if ok and engine.last_haunt_action_succeeded():
            traitor = self._traitor(engine)
            if traitor is not None:
                flags = engine._haunt_flags()
                flags["detected_room"] = traitor.room_key
                detected_by = flags.setdefault("detected_by", [])
                if str(player.id) not in detected_by:
                    detected_by.append(str(player.id))
                room = engine.state.board.get(traitor.room_key)
                engine._log(
                    f"{player.name} 捕捉到了空气里那一丝移动——叛徒就在"
                    f"{room.name if room else traitor.room_key}。"
                )
        return ok

    # ------------------------------------------------------------- 机器人
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p52：英雄胜 = 叛徒死亡——有线索就扑上去（射程内才由画像放行攻击）。"""
        if player.dead or player.role != "hero":
            return []
        traitor = self._traitor(engine)
        if traitor is None:
            return []
        return [f"__room__{traitor.room_key}"]

    # ------------------------------------------------------------- 进度摘要
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        """公开信息：叛徒是否已被锁定、锁定在哪一间（p52 侦测的成果）。"""
        flags = engine._haunt_flags()
        traitor = self._traitor(engine)
        if flags.get("detected_room") and traitor is not None:
            if flags.get("detected_room") == traitor.room_key:
                room = engine.state.board.get(traitor.room_key)
                return [f"叛徒已被锁定：{room.name if room else traitor.room_key}。"]
            return ["线索过时了——叛徒已经转移，需要重新侦测（知识 3+）。"]
        return ["还没有叛徒的线索：侦测叛徒（知识 3+）可以锁定 TA 的位置。"]

    def check_victory(self, engine: Any) -> bool:
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        traitor_alive = any(p.role == "traitor" and not p.dead for p in engine.state.players)
        # p52：英雄胜利条件 = 叛徒死亡（"You Win When … the traitor is dead."）。
        # 显式接管判定，不再依赖引擎「叛徒死亡→英雄胜」的通用兜底。
        if heroes_alive and not traitor_alive:
            engine._set_winner("heroes", "隐形的杀手终于现形了——他的尸体说明了一切。")
            return True
        # p123：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "隐形的杀手收割了最后的猎物。")
            return True
        return False
