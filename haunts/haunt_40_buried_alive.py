"""BuriedAliveMode（剧本 40）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    HauntAction,
)


class BuriedAliveMode(GenericModeHandler):
    """剧本 40 活埋（Buried Alive）。

    权威原文：英雄手册 p51 / 叛徒手册 p122。

    核心机制（M10-35 由 stub 补全为真实实现）：
    · 埋人（p122）：叛徒在"作祟开始前已发现的地下室房间"里秘密选一间埋下
      朋友；地下室不足 5 间时先把地下室房间补进场（含楼梯平台）再选。
    · 计时（p122）：叛徒回合结束时 Turn/Damage 轨 +1，掷等于轨位的骰子，
      被埋者累计受到等量物理伤害；累计 12 点即死亡 → 叛徒胜。
    · 搜查（p51）：英雄在地下室房间里做知识 3+ 搜查——成功且正好是埋葬室
      则找到；成功但不是则排除该房间；失败可换个回合再来。
    · 挖掘（p51）：找到埋葬室后，房内英雄力量 4+ 挖掘，成功 +1 进度；
      进度 = 作祟开始时玩家人数 → 英雄胜。
    · 通灵板（p51）：持通灵板的英雄可行动使用：理智 7+ 直接得知埋葬室；
      5-6 让被埋者回复 2 骰伤害；3-4 / 0-2 无效果。

    已知简化：
        · 原版"每回合可以搜查多间房"收窄为引擎的"每人每回合一次剧本行动"。
        · 通灵板 3-4 段（移动任意探险者 3 格）未建模；"不能主动交出/丢弃"
          未在物品层拦截；叛徒"造成 2+ 伤害可抢通灵板"未建模。
        · 被埋者伤害用引擎轨道记账（原版是叛徒纸笔记录），数字对双方可见。
        · 已排除的地下室房间不再重复提供搜查（原版允许，但再搜没有意义）。
    """

    mode = "buried_alive"

    SPIRIT_BOARD = "omen_spirit_board"
    BASEMENT_FLOOR = -1
    BASEMENT_MIN = 5

    # ------------------------------------------------------------- 地形
    def _basement_rooms(self, engine: Any) -> list[Any]:
        return [room for room in engine.state.board.values() if room.floor == self.BASEMENT_FLOOR]

    def _ensure_basement(self, engine: Any, anchor: str) -> None:
        """p122：地下室不足 5 间时，先把地下室房间补进场再选埋葬室。

        优先用 `_attach_template_adjacent` 接到楼梯平台旁边（门对门连通）——
        `_ensure_room_in_play` 有时会把房间放成"挨着但没有门"的孤岛（实测
        seed=113 的吱呀走廊），那样补出来的房间英雄根本走不到。
        """
        candidates = sorted(
            template.id
            for template in engine.catalog.room_templates.values()
            if template.floor == self.BASEMENT_FLOOR and template.id != "basement_landing"
        )
        engine.rng.shuffle(candidates)
        landing = next(
            (
                room.key
                for room in self._basement_rooms(engine)
                if room.template_id == "basement_landing"
            ),
            anchor,
        )
        for template_id in candidates:
            if len(self._basement_rooms(engine)) >= self.BASEMENT_MIN:
                break
            if engine._attach_template_adjacent(template_id, landing) is None:
                engine._ensure_room_in_play(template_id, anchor)

    def _reachable_basement_rooms(self, engine: Any, anchor: str) -> list[Any]:
        """过滤掉孤立板块——埋人处必须走得到，否则英雄永远挖不出来。"""
        rooms = self._basement_rooms(engine)
        reachable = [
            room
            for room in rooms
            if room.key == anchor or engine._path_length(anchor, room.key) < 9999
        ]
        reachable = reachable or rooms
        # 楼梯平台算地下室房间（计入 5 间），但埋人处优先选别的房间。
        return [room for room in reachable if room.template_id != "basement_landing"] or reachable

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        self._ensure_basement(engine, room_key)
        candidates = self._reachable_basement_rooms(engine, room_key)
        burial = engine.rng.choice(candidates) if candidates else None
        flags["burial_room"] = burial.key if burial is not None else ""
        flags["burial_found"] = False
        flags["ruled_out"] = []
        flags["bury_timer"] = 0
        # 不记录房间位置（日志会泄密）；英雄靠搜查或通灵板找出埋葬室。
        engine._log("叛徒数着泥土下的呼吸声——没有人知道那间屋子在哪。")

    # ------------------------------------------------------------- 回合结束
    def on_turn_end(self, engine: Any, player: Any) -> None:
        """p122：叛徒回合结束时推进 Turn/Damage 轨并结算被埋者的伤害。

        叛徒出局后由轮转顺序里第一位存活玩家代推（项目惯例，同 22/30/33 号）：
        泥土下的倒计时是剧本自身的钟——叛徒倒下不等于朋友得救。缺这条时，
        力 1 的英雄（1 骰永远够不到 4+）会永远卡在"挖不动"上，对局再也收不了场
        （M10-52 seed107/3p 实测 300 回合跑不完，两人在地下室里挖了 40 个回合）。
        """
        if player.dead:
            return
        traitor_alive = any(p.role == "traitor" and not p.dead for p in engine.state.players)
        if player.role == "traitor":
            advance = True
        elif not traitor_alive:
            first_alive = next(
                (
                    pid
                    for pid in engine.state.turn_order
                    if any(p.id == pid and not p.dead for p in engine.state.players)
                ),
                None,
            )
            advance = player.id == first_alive
        else:
            advance = False
        if not advance:
            return
        flags = engine._haunt_flags()
        timer = int(flags.get("bury_timer", 0)) + 1
        flags["bury_timer"] = timer
        rolled = engine.roll_damage_dice(timer, f"活埋伤害（轨位 {timer}）")
        engine._advance_haunt_track("burial_damage", rolled)
        engine._log(f"泥土下面传来沉闷的声响——被埋的人挨过了 {rolled} 点伤害。")
        engine.check_victory()

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        if player.dead or player.role != "hero":
            return []
        flags = engine._haunt_flags()
        actions: list[Any] = []
        room = engine.state.board.get(player.room_key)
        found = bool(flags.get("burial_found"))
        if (
            room is not None
            and room.floor == self.BASEMENT_FLOOR
            and not found
            and room.key not in set(flags.get("ruled_out", []))
        ):
            actions.append(
                HauntAction("h40_search", "搜查房间", "知识 3+：成功即可确认这里是不是埋葬室。")
            )
        if found and flags.get("burial_room") == player.room_key:
            actions.append(
                HauntAction(
                    "h40_dig",
                    "挖出朋友",
                    "力量 4+：每成功一次推进一格，集满开局玩家人数即救出朋友。",
                )
            )
        if self.SPIRIT_BOARD in player.items and not found:
            actions.append(
                HauntAction(
                    "h40_spirit_board",
                    "使用通灵板",
                    "理智 7+ 直接得知埋葬室；5-6 让朋友回复 2 骰伤害。",
                )
            )
        return actions

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        if action_id == "h40_search":
            room = engine.state.board.get(player.room_key)
            if (
                player.role != "hero"
                or room is None
                or room.floor != self.BASEMENT_FLOOR
                or flags.get("burial_found")
                or room.key in set(flags.get("ruled_out", []))
            ):
                return False
            if engine._resolve_check(player, "knowledge", 3, "搜查埋葬室"):
                if flags.get("burial_room") == room.key:
                    flags["burial_found"] = True
                    engine._log("挪开最后一块松动的石板——下面真的有人！")
                else:
                    ruled = list(flags.get("ruled_out", []))
                    ruled.append(room.key)
                    flags["ruled_out"] = ruled
                    engine._log("地面是实心的——朋友不在这里。")
            return True
        if action_id == "h40_dig":
            if not flags.get("burial_found") or flags.get("burial_room") != player.room_key:
                return False
            if engine._resolve_check(player, "might", 4, "挖开泥土"):
                engine._advance_haunt_track("dig_progress", 1)
                engine._log(f"{player.name} 又挖深了一尺——土下的敲击声更近了。")
            return True
        if action_id == "h40_spirit_board":
            if self.SPIRIT_BOARD not in player.items or flags.get("burial_found"):
                return False
            total = engine.roll_dice(engine._effective_stat(player, "sanity"), "通灵板")
            if total >= 7:
                flags["burial_found"] = True
                engine._log("指针疯狂旋转，最后死死停在一个方向——找到那间屋子了。")
            elif total >= 5:
                heal = engine.roll_dice(2, "通灵板安抚")
                engine._advance_haunt_track("burial_damage", -heal)
                engine._log(f"灵板传来微弱的回应——朋友还活着，伤痛减轻了 {heal} 点。")
            return True
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        # p51：挖出朋友（进度 = 作祟开始时玩家人数）→ 英雄胜
        if engine._haunt_track_value("dig_progress") >= engine._haunt_track_target("dig_progress"):
            engine._set_winner("heroes", "指尖触到木板的裂缝——朋友被拖出了黑暗。")
            return True
        # p122：被埋者累计 12 点伤害 → 死亡，叛徒胜
        if engine._haunt_track_value("burial_damage") >= engine._haunt_track_target("burial_damage"):
            engine._set_winner("traitor", "最后一铲泥土落下——房子又多了一个沉默的住户。")
            return True
        # p122：英雄全灭 → 叛徒胜
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "没有人能从冰冷的泥土中回来了。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p51 只认"挖出朋友"。
        # （叛徒死后伤害轨不再推进，但挖掘仍须完成。）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- 机器人
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.dead or player.role != "hero":
            return []
        flags = engine._haunt_flags()
        if flags.get("burial_found"):
            key = flags.get("burial_room")
            return [f"__room__{key}"] if key else []
        ruled = set(flags.get("ruled_out", []))
        return [
            f"__room__{room.key}"
            for room in self._basement_rooms(engine)
            if room.key not in ruled
        ]

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        damage = engine._haunt_track_value("burial_damage")
        digs = engine._haunt_track_value("dig_progress")
        need = engine._haunt_track_target("dig_progress")
        where = "埋葬室已找到" if flags.get("burial_found") else "埋葬室尚未找到"
        return [f"{where}；挖掘进度 {digs}/{need}，被埋朋友的伤害 {damage}/12。"]
