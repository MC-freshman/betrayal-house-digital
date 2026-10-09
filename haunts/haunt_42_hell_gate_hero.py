"""HellGateHeroMode（剧本 42）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class HellGateHeroMode(GenericModeHandler):
    """剧本 42 地狱之门英雄（Comes the Hero）。

    权威原文：英雄手册 p53 / 叛徒手册 p124。

    · 雕像（Statue token）：放在作祟揭示房间。英雄把圣徽/斧/水晶球/
      古书放入雕像手中 → 雕像活化（审判官/战士/先知/巫师）。
    · 活化雕像移动：同房英雄做知识或理智检定，格数=结果
      （move_statue 行动）。
    · 雕像攻击：与叛徒同房时降低叛徒对应属性 1 点
      （审判官→Speed，战士→Might，先知→Sanity，巫师→Knowledge）。
    · 叛徒无敌：不可被攻击（attack_allowed 返回 False），
      直到任一属性降至 0 → 可被正常攻击。
    · 叛徒胜利：杀死英雄 + 尸体带到特定房间 + 检定 4+ → 地狱门打开。
      简化为"叛徒回合开始如果同房有英雄则掷骰攻击"（bot 局用）。
    · 简化：雕像不会移动寻路（只在同房英雄的房间之间移动——由
      move_statue 行动控制）；叛徒门开启的详细流程简化。
    """

    mode = "hell_gate_hero"

    STATUE_ITEMS = {
        "omen_holy_symbol": ("judge", "审判官", "speed"),
        "item_axe": ("warrior", "战士", "might"),
        "omen_crystal_ball": ("seer", "先知", "sanity"),
        "omen_book": ("wizard", "巫师", "knowledge"),
    }

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["statue_room"] = room_key
        flags["statue_form"] = None  # None = 未活化
        flags["gate_open"] = False
        engine.spawn_token("statue", label="雕像", role="marker", room_key=room_key)
        engine._log("一尊雕像伸出手指，底座上刻着——'击败不可战胜之人'。")

    # ------------------------------------------------------------- 内部
    def _statue_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("statue_room")

    def _traitor_vulnerable(self, engine: Any) -> bool:
        """叛徒任一属性降至 0 → 可被攻击。"""
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is None:
            return True
        return any(v <= 0 for v in traitor.stats.values())

    # ------------------------------------------------------------- 攻击规则
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p53：叛徒不可被攻击，直到雕像削弱其属性至 0。"""
        if isinstance(getattr(target, "role", None), str) and target.role == "traitor":
            return self._traitor_vulnerable(engine)
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        statue_room = self._statue_room(engine)
        for action in actions:
            if action.id == "animate_statue":
                if player.room_key != statue_room or flags.get("statue_form"):
                    continue
                has_item = any(item in player.items for item in self.STATUE_ITEMS)
                if not has_item:
                    continue
            if action.id == "move_statue":
                if player.role != "hero" or not flags.get("statue_form"):
                    continue
                if player.room_key != flags.get("statue_room"):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        statue_room = self._statue_room(engine)
        if action_id == "animate_statue":
            if player.room_key != statue_room or flags.get("statue_form"):
                return False
            item = next((i for i in player.items if i in self.STATUE_ITEMS), None)
            if item is None:
                engine._log("你没有可以放入雕像手中的物品。")
                return False
            form_key, form_name, drain_stat = self.STATUE_ITEMS[item]
            flags["statue_form"] = form_key
            flags["drain_stat"] = drain_stat
            player.items.remove(item)
            engine._log(f"{player.name} 把{engine.catalog.cards[item].name}放入雕像手中——雕像化身为{form_name}！")
            return True

        if action_id == "move_statue":
            if not flags.get("statue_form") or player.room_key != flags.get("statue_room"):
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                roll = engine._effective_stat(player, "knowledge") if flags.get("statue_form") == "wizard" else engine._effective_stat(player, "sanity")
                # 简化：向最近英雄（叛徒）方向移动 min(roll, path)
                traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
                if traitor is not None and traitor.room_key != statue_room:
                    path = engine._shortest_path(statue_room, traitor.room_key)
                    if len(path) > 1:
                        dest = path[min(len(path) - 1, max(1, roll))]
                        flags["statue_room"] = dest
                        engine._log(f"雕像移动到了{engine.state.board[dest].name}。")
                # 雕像与叛徒同房：降低对应属性
                traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
                if traitor is not None and traitor.room_key == flags.get("statue_room"):
                    drain = flags.get("drain_stat", "might")
                    engine._apply_stat_loss(traitor, drain, 1)
                    engine._log(f"雕像削弱了叛徒的{drain}（-1）。")
                    if self._traitor_vulnerable(engine):
                        engine._log("叛徒的防线被突破了——TA 现在可以被攻击！")
            return ok

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 机器人
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p53：英雄胜线＝给雕像放圣物激活它 → 推着雕像去撞叛徒 → 削弱到能打。

        本类既没有 `key_rooms`（rule_data 为空）也没有画像目标，机器人因此
        没有任何剧本目标：18 局实测雕像**一次都没被激活**（`statue_form` 恒
        为 None、`雕像削弱` 0 次），英雄只是在房子里无目的游荡（seed107/6p
        在五芒星室↔舞厅之间震荡 25 次），胜负全看叛徒会不会死于房间/事件伤害。
        """
        if player.dead or player.role != "hero":
            return []
        traitor = next(
            (p for p in engine.state.players if p.role == "traitor" and not p.dead), None
        )
        # 叛徒已被雕像削到可以被攻击 → 收尾（画像同时放开了打叛徒）
        if self._traitor_vulnerable(engine) and traitor is not None:
            return [f"__room__{traitor.room_key}"]
        statue_room = self._statue_room(engine)
        if not statue_room:
            return []
        if not engine._haunt_flags().get("statue_form"):
            # 雕像还没活化：只有**手里拿着圣物**的英雄值得去（别人过去也做不了
            # 事，只会在门口来回晃——seed113/6p 实测风琴房×16 的震荡就是没带
            # 物品的英雄被目标钉在那儿）。没带圣物的交给通用目标：rule_data 的
            # required_cards 会把地上的圣物标成"去捡回来"。
            if not any(item in player.items for item in self.STATUE_ITEMS):
                return []
        # 已活化：英雄得站在雕像旁边才能推动它（move_statue 要求同房）
        return [f"__room__{statue_room}"]

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        traitor_alive = any(p.role == "traitor" and not p.dead for p in engine.state.players)
        # p53：英雄胜利条件 = 叛徒死亡（"You Win When … the traitor is dead."）。
        # 显式接管判定，不再依赖引擎「叛徒死亡→英雄胜」的通用兜底。
        if heroes_alive and not traitor_alive:
            engine._set_winner("heroes", "雕像手中的圣物开始发光——地狱之门缓缓合拢。")
            return True
        if not heroes_alive:
            engine._set_winner("traitor", "地狱之门打开了。")
            return True
        return super().check_victory(engine)
