"""FleshwalkerMode（剧本 12）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class FleshwalkerMode(GenericModeHandler):
    """剧本 12 肉行者（Fleshwalkers，即"邪恶双胞胎"）。

    权威原文：英雄手册 p23 / 叛徒手册 p94。

    本剧本没有叛徒：每个探险者都要面对自己的邪恶双胞胎。引擎每次作祟
    都会指定一名"潜伏叛徒"，本模式在 setup 里把他降回英雄（同剧本 9），
    并清空 traitor_id；胜负全部由本模式显式判定。

    · 双胞胎（p23）：用 shadow 模板承载，属性 = 对应探险者作祟开局值，
      **整局冻结**；全部生成在门厅；不能携带物品。
    · 行动时序（p23 "take their monster turn after the haunt revealer's
      turn"）：引擎轮转回合序恰好让揭示者最后行动、怪物阶段紧随其后，
      无需额外处理。
    · 双胞胎行为：永远沿最短路追自己的本体；同房间优先攻击本体，否则
      随机攻击房内一名探险者（引擎 rng，种子可复现）。本体死亡后，该
      玩家控制这只双胞胎攻击其他探险者（电子版 bot 近似：追最近的其他
      活人）。
    · 水晶球规则（p23）：
        - 无球与**自己的**双胞胎交手：无论谁赢，自己四属性各 -1
          （on_attack_resolved 钩子，平手不结算）；
        - 无球击败自己的双胞胎 → 击晕；持球击败自己的双胞胎 → 杀死；
        - 击败**别人的**双胞胎 → 击晕；持球且其本体已死 → 杀死；
        - 昏迷的双胞胎只有持球者能攻击（attack_allowed），且它防守时不
          反击（monster_counterattack_disabled）。
    · 英雄胜：双胞胎全部被消灭且至少一名英雄存活；全部探险者死亡 =
      双胞胎获胜。无叛徒，吸收引擎"叛徒缺席→英雄胜"兜底。
    """

    mode = "fleshwalkers"

    TWIN = "shadow"            # 双胞胎用 shadow 模板承载，数值逐只覆盖
    CRYSTAL_BALL = "omen_crystal_ball"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["twin_of"] = {}
        flags["twins_killed"] = 0
        latent = next((p for p in engine.state.players if p.role == "traitor"), None)
        if latent is not None:
            latent.role = "hero"
            engine.state.traitor_id = None
        entrance = next(
            (k for k, r in engine.state.board.items() if r.template_id == "entrance_hall"),
            room_key,
        )
        # p23：双胞胎属性 = 对应探险者作祟开局值，且整局冻结（引擎不会
        # 主动改怪物属性，冻结天然成立）
        for player in engine.state.players:
            spec = {
                "template_id": self.TWIN,
                "name": f"邪恶双胞胎·{player.name}",
                "speed": int(player.stats.get("speed", 2)),
                "might": int(player.stats.get("might", 2)),
                "sanity": int(player.stats.get("sanity", 2)),
                "knowledge": int(player.stats.get("knowledge", 2)),
                "can_carry_items": False,
            }
            monster = engine._spawn_single_haunt_monster(spec, entrance)
            if monster is not None:
                flags["twin_of"][str(monster.id)] = player.id
        count = len(flags["twin_of"])
        engine._log(f"门厅里站着一排熟得不能再熟的身影——{count} 个邪恶双胞胎睁开了眼睛。")

    # ------------------------------------------------------------- 内部
    def _counterpart(self, engine: Any, monster: Any) -> Any | None:
        pid = engine._haunt_flags().get("twin_of", {}).get(str(getattr(monster, "id", "")))
        if pid is None:
            return None
        return next((p for p in engine.state.players if p.id == int(pid)), None)

    # ------------------------------------------------------------- 行为
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.TWIN:
            return False
        counterpart = self._counterpart(engine, monster)
        target_room: str | None = None
        if counterpart is not None and not counterpart.dead:
            target_room = counterpart.room_key  # p23：永远追本体
        else:
            # 本体已死：由该玩家控制，追杀最近的其他活人（bot 近似）
            others = [
                p for p in engine.state.players
                if not p.dead and p.room_key != getattr(monster, "room_key", "")
            ]
            if others:
                others.sort(key=lambda p: (engine._path_length(monster.room_key, p.room_key), p.id))
                target_room = others[0].room_key
        if target_room and target_room != monster.room_key:
            path = engine._shortest_path(monster.room_key, target_room)
            if len(path) > 1:
                monster.room_key = path[min(len(path) - 1, rolled)]
                engine._log(f"邪恶双胞胎逼近{engine.state.board[monster.room_key].name}。")
        return True

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.TWIN:
            return False
        in_room = [
            p for p in engine.state.players
            if not p.dead and p.room_key == monster.room_key
        ]
        if not in_room:
            return True
        counterpart = self._counterpart(engine, monster)
        if (
            counterpart is not None and not counterpart.dead
            and counterpart.room_key == monster.room_key
        ):
            victim = counterpart  # p23：可能的话永远攻击本体
        else:
            victim = in_room[engine.rng.randrange(len(in_room))]  # 随机选一个
        twin_roll = engine._roll_monster_attack(monster, "might")
        hero_roll = engine._roll_attack(victim, "might")
        engine._log(f"{monster.name} 扑向 {victim.name}：{twin_roll} 对 {hero_roll}。")
        if twin_roll > hero_roll:
            engine._deal_damage(victim, "physical", twin_roll - hero_roll, source=monster.name)
        elif twin_roll < hero_roll:
            engine._stun_monster(monster, 1)
        return True

    # ------------------------------------------------------------- 攻击规则
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p23：昏迷的双胞胎只有持水晶球者能攻击。"""
        if _monster_id(target) == self.TWIN and int(getattr(target, "stunned_turns", 0)) > 0:
            return self.CRYSTAL_BALL in attacker.items
        return True

    def monster_counterattack_disabled(self, engine: Any, monster: Any) -> bool:
        """p23：昏迷双胞胎防守时用常规骰，但赢了也不造成伤害。"""
        return _monster_id(monster) == self.TWIN and int(getattr(monster, "stunned_turns", 0)) > 0

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        """p23：无球与自己的双胞胎交手，无论谁赢四属性各 -1。"""
        if _monster_id(target) != self.TWIN:
            return
        counterpart = self._counterpart(engine, target)
        if counterpart is None or counterpart.id != getattr(attacker, "id", None):
            return  # 只对"自己的双胞胎"生效
        if self.CRYSTAL_BALL in attacker.items:
            return
        for stat in ("speed", "might", "sanity", "knowledge"):
            engine._apply_stat_loss(attacker, stat, 1)
        engine._log(f"{attacker.name} 在与自己的双胞胎交手中心神受创（四属性各 -1）。")

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p23：击败双胞胎默认击晕；持球（自己/本体已死）则杀死。"""
        if _monster_id(monster) != self.TWIN:
            return False
        attacker = None
        active_id = getattr(engine, "_active_player_id", None)
        if active_id is not None:
            attacker = engine.state.players[active_id]
        holder = attacker is not None and self.CRYSTAL_BALL in attacker.items
        counterpart = self._counterpart(engine, monster)
        own = counterpart is not None and attacker is not None and attacker.id == counterpart.id
        counterpart_dead = counterpart is None or counterpart.dead
        if holder and (own or counterpart_dead):
            monster_id = getattr(monster, "id", None)
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
            ]
            flags = engine._haunt_flags()
            flags.get("twin_of", {}).pop(str(monster_id), None)
            engine._advance_haunt_track("twins_killed", 1)
            engine._log("水晶球迸出强光——邪恶双胞胎被彻底湮灭了！")
            engine.check_victory()
            return True
        return False  # 默认击晕

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes_alive = any(p.role == "hero" and not p.dead for p in engine.state.players)
        if (
            engine._haunt_track_value("twins_killed") >= engine._haunt_track_target("twins_killed")
            and heroes_alive
        ):
            engine._set_winner("heroes", "所有邪恶双胞胎都被消灭，活下来的人面面相觑。")
            return True
        if not heroes_alive:
            engine._set_winner("traitor", "探险者全军覆没——房子里只剩下他们的双胞胎。")
            return True
        return True  # 本剧本无叛徒，吸收引擎"叛徒缺席即英雄胜"兜底
