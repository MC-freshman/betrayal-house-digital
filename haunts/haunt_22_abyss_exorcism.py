"""AbyssExorcismMode（剧本 22）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .haunt_08_exorcism import ExorcismMode  # noqa: F401  继承自其他具体 handler


class AbyssExorcismMode(ExorcismMode):
    """剧本 22 深渊回望（The Abyss Gazes Back）。

    权威原文：英雄手册 p33 / 叛徒手册 p104。

    复用剧本 8 的驱魔底座（一次性来源、每人每回合一次、成功后放检定令牌、
    满玩家人数即完成），p33 把理智物品来源从灵应板换成**戒指**。本次新增：

    · 深渊起点（p104）：地下室里无人、带预兆或事件符号的房间；一间都没有就
      从房间牌堆拿一张合法的地下室房放上（与 `_ensure_room_in_play` 同做法）。
    · 叛徒首个回合结束翻掉起点房，之后每个叛徒回合结束推进深渊回合轨（从 1 起）。
    · 坍塌速率（p104）：每位玩家回合结束时——第 2 回合塌 1 间、第 3 回合掷 2 骰、
      第 4 回合 3 骰、第 5 回合起 4 骰（骰面 0-2，所以可能一间都不塌）。
      只能沿已有深渊的正交邻格扩散；整层塌完升到上一层，从"无人且留着未探索
      门口"的房间开始（引擎 `_collapse_adjacent_rooms` 的升层死代码已在
      M10-72 修掉，本剧本直接调用它即可）。
      注意：叛徒阵亡后其回合消失，深渊回合轨随之冻结（p104 的速率只随该轨
      上升），所以此时坍塌速率停在冻结值——但每个玩家回合照常塌房，深渊
      仍会一路吃到英雄死光（p104 "eventually win even if you are killed"）。
    · 房内有人（含叛徒）：速度 4+ 逃进相邻、有门连通、已发现的房间，否则坠亡。
    · 圣徽拖延（p33）：持圣徽且站在深渊邻格，可弃掉圣徽代替翻牌，并阻止房屋
      继续坍塌到自己下个回合结束；深渊回合轨照常推进。
    · 检定令牌一旦放下就计入总数：来源房间随后塌掉也不作废（p33 明文），
      电子版天然满足——令牌与 `used_exorcism_sources` 都不依赖房间存活。
    · 胜负：驱魔满员 → 英雄胜；英雄全灭 → 叛徒胜。叛徒被塌死也照常扩散
      （p104 "You may still collapse rooms on your turn and eventually win
      even if you are killed"），故吸收引擎"叛徒死亡即英雄胜"的兜底。

    已知简化：
        · 深渊邻格挑哪间塌用确定性顺序（按坐标排序取第一间），原版由叛徒任选；
          人类叛徒暂无"选哪间塌"的弹窗（接 prompter 即可支持）。
        · 机器人不会主动使用"献出圣徽"，该行动目前只对人类玩家有意义。
        · 本剧本没有怪物，威胁完全由坍塌承担，引擎的怪物回合对本局无操作。
    """

    mode = "abyss_exorcism"

    SACRIFICE_ACTION = "sacrifice_holy_symbol"
    SANITY_ITEM_SOURCES = ["omen_holy_symbol", "omen_ring"]
    ALL_SOURCES = (
        ExorcismMode.SANITY_ROOM_SOURCES + SANITY_ITEM_SOURCES
        + ExorcismMode.KNOWLEDGE_ROOM_SOURCES + ExorcismMode.KNOWLEDGE_ITEM_SOURCES
    )

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("used_exorcism_sources", [])
        flags["abyss_room"] = self._pick_abyss_room(engine, room_key)
        flags["abyss_started"] = False
        flags["abyss_paused_until"] = 0
        start = engine.state.board.get(flags["abyss_room"])
        engine._log(f"地板在{start.name if start else '地下室'}裂开，下面不是地基，是火。")

    def _pick_abyss_room(self, engine: Any, haunt_room_key: str) -> str:
        """p104：地下室里无人、带预兆或事件符号的房间；没有就从牌堆补一间。"""
        occupied = {p.room_key for p in engine.state.players if not p.dead}
        basement = [
            room for room in engine.state.board.values()
            if room.floor == -1 and room.revealed and room.key not in occupied
        ]
        with_symbol = sorted(room.key for room in basement if room.symbol in ("omen", "event"))
        if with_symbol:
            return with_symbol[0]
        if basement:
            return sorted(room.key for room in basement)[0]
        deck_id = next(
            (
                template_id for template_id in engine.state.room_deck
                if template_id in engine.catalog.room_templates
                and engine.catalog.room_templates[template_id].floor == -1
            ),
            "",
        )
        placed = engine._ensure_room_in_play(deck_id, haunt_room_key) if deck_id else None
        return placed or haunt_room_key

    # ------------------------------------------------------- 深渊每回合扩散
    def on_turn_end(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        first_traitor_turn = False
        if player.role == "traitor":
            if not flags.get("abyss_started"):
                flags["abyss_started"] = True
                first_traitor_turn = True
                start = flags.get("abyss_room")
                if start:
                    engine._collapse_room(str(start), cause="地狱之门")
            engine._advance_haunt_track("abyss_turn", 1)
        if first_traitor_turn:
            return  # 第 1 回合只开洞；按速率塌房从第 2 回合开始（p104）
        turn = engine._haunt_track_value("abyss_turn")
        if turn <= 0:
            return  # 第 1 回合不塌房（p104 "starting on Turn 2"）
        if turn <= int(flags.get("abyss_paused_until", 0) or 0):
            engine._log("圣徽烧成的灰把裂缝暂时按住了。")
            return
        count = 1 if turn == 1 else engine.roll_dice(min(4, turn), "深渊扩散")
        if count > 0:
            engine._collapse_adjacent_rooms(count)

    # --------------------------------------------------------- 圣徽拖延
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        if self._next_to_abyss(engine, player):
            return actions
        return [action for action in actions if action.id != self.SACRIFICE_ACTION]

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id != self.SACRIFICE_ACTION:
            return super().perform_action(engine, player, action_id, data)
        if "omen_holy_symbol" not in player.items:
            engine._log("你没有圣徽可以献出。")
            return False
        if not self._next_to_abyss(engine, player):
            engine._log("你脚下没有紧邻的深渊，圣徽无处可献。")
            return False
        engine._discard_card_from_player(player, "omen_holy_symbol", return_to_room=False)
        engine._haunt_flags()["abyss_paused_until"] = engine._haunt_track_value("abyss_turn") + 1
        engine._mark_haunt_action_used(player)
        engine._log("圣徽在你手里烧成灰烬，塌陷停了一拍——但深渊的时钟没有停。")
        return True

    def _next_to_abyss(self, engine: Any, player: Any) -> bool:
        return any(engine._is_collapsed(key) for key in engine._grid_neighbors(player.room_key))

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("exorcism_successes") >= engine._haunt_track_target("exorcism_successes"):
            engine._set_winner("heroes", "最后一句祷词落下，房子不再颤抖，灰雾退了回去，红光熄灭。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "地板整片垮落，最后几个灵魂一起坠进了火湖。")
            return True
        return True  # 叛徒死了深渊照常扩散：吸收引擎兜底
