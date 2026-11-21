"""WW 剧本 109《主人的风流韵事之一》（One of the Master's Affairs，官方 #89，作者 Mike Selinker）。

骨架剧本：双进度轨 + 检定型剧本行动（haunt_rules._WW_SCENARIO_TABLE[109]）。
官方触发：房间：Balcony、Dining Room、Dungeon、Kitchen；预兆：Photograph。
官方英雄胜利：全部存活英雄从（上锁的）前门逃出（Stage a Farce 演戏开锁）
官方叛徒设定：雨夜留宿的怪医生 The Doctor，用前任住客尸体拼缝怪物（驼背仆人 Rough Ralph 等）
引擎侧简化建模与官方差异逐条登记在 haunt_rules.py 的 engine_note。
"""
from __future__ import annotations

from typing import Any

from .base import GenericModeHandler


class WWHaunt109Mode(GenericModeHandler):
    """剧本 109「One of the Master's Affairs」的 mode handler。

    行动与进度轨走 GenericModeHandler 的通用 rule_data 执行；这里只
    接管胜负判定的兜底分支：叛徒死亡 → 英雄立即获胜（官方剧本的通用
    击败线），其余条件交给 rule_data.win_conditions。
    """

    mode = "ww_haunt_109"

    def check_victory(self, engine: Any) -> bool:
        """剧本 109 胜负判定：叛徒（traitor）死亡时英雄立即获胜。"""
        traitor_id = engine.state.traitor_id
        if traitor_id is not None:
            traitor = engine.state.players[traitor_id]
            if traitor.dead:
                engine._set_winner(
                    "heroes",
                    "叛徒被击败：全部存活英雄从（上锁的）前门逃出（Stage a Farce 演戏开锁）",
                )
                return True
        return engine._check_generic_haunt_victory()

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        """进入作祟时执行剧本入口函数（校验胜负条件已就位）。"""
        haunt_haunt109(engine)


def haunt_haunt109(engine: Any) -> dict:
    """剧本 109 的引擎入口：设置/校验叛徒与英雄的胜负条件。

    rule_data.win_conditions 在作祟初始化（engine._initialize_haunt_rules）
    时已写入 state.meta；这里显式校验两条胜负条件（hero / traitor）都在，
    返回给审计与测试断言。
    """
    rule = engine._generic_haunt_rule()
    conditions = rule.get("win_conditions") or []
    if not any(str(condition.get("winner")) == "heroes" for condition in conditions):
        raise RuntimeError("剧本 109 缺少英雄胜负条件")
    if not any(str(condition.get("winner")) == "traitor" for condition in conditions):
        raise RuntimeError("剧本 109 缺少叛徒胜负条件")
    return {"win_conditions": conditions}
