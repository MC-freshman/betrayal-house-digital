"""DeathDanceMode（剧本 9）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class DeathDanceMode(GenericModeHandler):
    """剧本 9 死亡之舞（The Dance of Death）。

    权威原文：英雄手册 p20 / 叛徒手册 p91。

    特色是"开局没有叛徒"：每位英雄在自己回合开始都可能被魔音诱惑成叛徒。
    引擎每次作祟都必然指定一名叛徒，本模式在 setup 里把引擎选出的这名
    玩家降回英雄（含清空 traitor_id），真正的叛徒由诱惑检定动态诞生。

    · 补房（p20）：五芒星室与舞厅不在场时从房间牌堆拉进场（引擎
      _ensure_room_in_play 放同楼层空位；原版"五芒星室放最远、舞厅接一楼
      任选房间"的精确选址省略，只保证房间到场）。
    · 抵抗诱惑（p20）：每位英雄（持圣徽者豁免）回合开始理智检定 4+；
      失败 → 若在舞厅，或理智被扣到骷髅格 → 当场堕落为叛徒；否则理智
      -1 并沿最短路线被迫走向舞厅。
    · 理智因其他原因降到骷髅格也堕落为叛徒（p20 "you also become
      insane"）。引擎死亡流程会把 0 属性判死，本模式只在回合开始兜底转
      化——中途被精神伤害直接打死仍走死亡流程（已知简化）。
    · 放逐提琴手（英雄胜，p20）：英雄把圣徽带进五芒星室后，同房任意英雄
      可做理智 5+ 检定（无需本人持徽）；成功在五芒星室放一枚理智令牌；
      令牌数 = 作祟开局人数 → 放逐成功。每人每回合只能尝试一步。
    · 持圣徽者不能自愿转交圣徽（引擎 item_trade_blocked 钩子）。
    · 叛徒每回合开始做力量检定：3+ 无碍；0-2 本回合不能移动且力量 -1
      （p91 "Dance until your feet go numb"）。
    · 叛徒胜：圣徽被毁（偷到手后在深渊/熔炉房/地下湖结束回合）或英雄全灭。
    · 已知简化：叛徒"速度对速度攻击、2+ 可改偷"（p91）属引擎攻击结算级
      改动，未接（同剧本 1 木乃伊专属战斗的处理方式）；第一个堕落者成为
      叛徒后，其余英雄诱惑失败只吃 1 点理智伤害并走向舞厅，不再二次转化
      （原版未说明多人堕落如何处理，电子版取单叛徒模型）。
    """

    mode = "delayed_traitor_relic"

    PENTAGRAM = "pentagram_chamber"
    BALLROOM = "ballroom"

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        engine._ensure_room_in_play(self.PENTAGRAM, room_key)
        engine._ensure_room_in_play(self.BALLROOM, room_key)
        ballroom_key = next(
            (k for k, r in engine.state.board.items() if r.template_id == self.BALLROOM),
            None,
        )
        engine.spawn_token("dark_fiddler", label="黑暗提琴手", role="marker",
                           room_key=ballroom_key or room_key)
        flags.setdefault("converted_traitor_id", None)
        flags.setdefault("holy_symbol_destroyed", False)
        latent = next((p for p in engine.state.players if p.role == "traitor"), None)
        if latent is not None:
            latent.role = "hero"
            engine.state.traitor_id = None
            engine._log("提琴手的旋律在每个心头埋下种子——目前还没有人堕落。")

    def item_trade_blocked(self, engine: Any, giver: Any, target: Any, card_id: str) -> bool:
        return card_id == "omen_holy_symbol" and giver.role == "hero"

    def _ballroom_key(self, engine: Any) -> str | None:
        return next(
            (k for k, r in engine.state.board.items() if r.template_id == self.BALLROOM), None
        )

    def _convert_to_traitor(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        flags["converted_traitor_id"] = player.id
        player.role = "traitor"
        engine.state.traitor_id = player.id
        engine._log(f"{player.name} 被提琴手的魔音攫住——他加入了死亡之舞！")
        engine.check_victory()

    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.dead:
            return
        if player.role == "traitor":
            # p91：叛徒每回合跳舞检定
            roll = engine._roll_attack(player, "might")
            if roll <= 2:
                player.movement_stopped = True
                engine._apply_stat_loss(player, "might", 1)
                engine._log(f"{player.name} 跳得双脚发麻（力量检定 {roll}）：本回合不能移动，力量 -1。")
            else:
                engine._log(f"{player.name} 在死亡之舞中旋舞（力量检定 {roll}）。")
            return
        # 英雄：理智已在骷髅格（其他原因所致）→ 堕落
        position = player.stat_positions.get("sanity")
        if position is not None and position <= 0 and not player.dead:
            self._convert_to_traitor(engine, player)
            return
        # 持圣徽者豁免诱惑检定
        if "omen_holy_symbol" in player.items:
            return
        if engine._resolve_check(player, "sanity", 4, "抵抗提琴手的诱惑"):
            return
        # 诱惑失败
        ballroom_key = self._ballroom_key(engine)
        if ballroom_key is not None and player.room_key == ballroom_key:
            self._convert_to_traitor(engine, player)
            return
        engine._apply_stat_loss(player, "sanity", 1)
        position = player.stat_positions.get("sanity")
        if position is not None and position <= 0:
            self._convert_to_traitor(engine, player)  # 理智扣到骷髅 = 堕落而非死亡
            return
        if ballroom_key is not None:
            path = engine._shortest_path(player.room_key, ballroom_key)
            if len(path) > 1:
                steps = max(1, player.stats.get("speed", 1))
                player.room_key = path[min(len(path) - 1, steps)]
                engine._log(
                    f"被魔音牵引的{player.name}身不由己地走向{engine.state.board[player.room_key].name}。"
                )

    HOLY_SYMBOL = "omen_holy_symbol"

    def _holy_symbol_in_play(self, engine: Any) -> bool:
        """圣徽是否已经进入对局（有人拿着，或掉在某间房里）。"""
        if any(
            self.HOLY_SYMBOL in p.items for p in engine.state.players if not p.dead
        ):
            return True
        return any(
            self.HOLY_SYMBOL in items for items in engine.state.room_items.values()
        )

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """圣徽还压在预兆牌堆里时，英雄必须继续探索去把它抽出来。

        p20 原文没有"搜牌堆"条款：圣徽只能靠正常抽预兆牌入手。缺了这条，
        英雄访到五芒星室就干等（seed113/3p 实测在五芒星室空站 351 次，
        圣徽整局留在牌堆里），放逐永远是 0/3。谁都可以去抽，所以这里对
        全体英雄放行。
        """
        if player.dead or player.role != "hero":
            return False
        if engine._haunt_flags().get("holy_symbol_destroyed"):
            return False
        if self._holy_symbol_in_play(engine):
            return False
        return self.HOLY_SYMBOL in engine.state.card_decks.get("omen", [])

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """给 bot 判寻路目标用：拿不到的那一步不算目的地。

        · 圣徽不在自己手上时，"毁掉圣徽"的房间不算目标（叛徒侧）。
        · 圣徽不在任何存活英雄手上时，"放逐提琴手"的五芒星室也不算目标
          （英雄侧）。p20 要求"同房任意英雄身上有圣徽"，而圣徽一旦落到
          叛徒手里就再也拿不回来（p91 只给叛徒"2+ 伤害改偷"的权利，英雄
          没有对等的抢夺条款）——英雄唯一的出路是**打死那个叛徒**，让圣徽
          掉在地上再捡起来（引擎死亡掉落令牌/卡牌）。不做这条时英雄整局
          钉在五芒星室里：实测 seed211/5p 打满 300 回合、全场只有 5 次攻击
          且全部没有目标，放逐进度 0/5。
        """
        if action_id == "destroy_holy_symbol":
            return self.HOLY_SYMBOL not in player.items
        if action_id == "banish_fiddler":
            return not self._hero_holds_symbol(engine)
        return False

    def _hero_holds_symbol(self, engine: Any) -> bool:
        return any(
            p.role == "hero" and not p.dead and self.HOLY_SYMBOL in p.items
            for p in engine.state.players
        )

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """圣徽在叛徒手上时，英雄的目标就是**那个叛徒**。

        p20 的放逐要求英雄把圣徽带进五芒星室，而圣徽可能被叛徒抢走/继承。
        此时英雄不该继续往五芒星室跑，而该去打掉持徽的叛徒——他一死圣徽
        就落在原地，谁进房谁捡（引擎 `_drop_inventory_on_death`）。
        """
        if player.dead or player.role != "hero":
            return []
        if engine._haunt_flags().get("holy_symbol_destroyed"):
            return []
        if self._hero_holds_symbol(engine):
            return []  # 已在英雄手里：交给静态目标（五芒星室）
        holder = next(
            (
                p for p in engine.state.players
                if p.role == "traitor" and not p.dead and self.HOLY_SYMBOL in p.items
            ),
            None,
        )
        return [f"__room__{holder.room_key}"] if holder is not None else []

    def bot_goal_suppressed(self, engine: Any, player: Any) -> bool:
        """叛徒没持圣徽时没有任何剧本目标房间（见 bot_action_blocked）。

        没有这条，key_rooms 保底会把五芒星室/舞厅/三间销毁房当成目的地，
        叛徒继续在空房间之间来回；正确行为是转头追杀英雄（通用追击逻辑）。
        """
        return player.role == "traitor" and self.HOLY_SYMBOL not in player.items
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "banish_fiddler":
                symbol_in_room = any(
                    other.role == "hero" and not other.dead
                    and other.room_key == player.room_key
                    and "omen_holy_symbol" in other.items
                    for other in engine.state.players
                )
                if not symbol_in_room:
                    continue  # 圣徽必须由某位英雄带进五芒星室
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "banish_fiddler":
            symbol_in_room = any(
                other.role == "hero" and not other.dead
                and other.room_key == player.room_key
                and "omen_holy_symbol" in other.items
                for other in engine.state.players
            )
            if not symbol_in_room:
                engine._log("需要有英雄把圣徽带进五芒星室才能尝试放逐。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine.last_haunt_action_succeeded():
                engine.spawn_token(
                    "sanity_check", label="放逐成功", role="check", room_key=player.room_key
                )
            return ok
        if action_id == "destroy_holy_symbol":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and not engine._haunt_flags().get("holy_symbol_destroyed"):
                engine._haunt_flags()["holy_symbol_destroyed"] = True
                engine._log("圣徽被抛入深渊——再也没有人能阻止死亡之舞了！")
            return ok
        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_flags().get("holy_symbol_destroyed"):
            engine._set_winner("traitor", "圣徽已毁，死亡之舞将永远继续。")
            return True
        if engine._haunt_track_value("fiddler_banishment") >= engine._haunt_track_target("fiddler_banishment"):
            engine._set_winner("heroes", "提琴手在圣咏中融化——死亡之舞终于落幕。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "所有人都加入了死亡之舞，再也停不下来。")
            return True
        return True  # 本剧本开局无叛徒，吸收引擎"叛徒缺席即英雄胜"兜底
