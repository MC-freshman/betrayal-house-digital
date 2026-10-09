"""GhostBrideMode（剧本 20）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class GhostBrideMode(GenericModeHandler):
    """剧本 20 幽灵新娘（Ghost Bride）。

    权威原文：英雄手册 p31 / 叛徒手册 p102。

    · 布点（p102）：教堂与地窖强制入场（_ensure_room_in_play）；新郎
      尸体令牌开局放地窖；新娘（ghost 模板承载，invulnerable——p102
      "cannot be damaged or stunned by any means"，以叛徒手册为准，
      含戒指理智攻击）生成在叛徒房间；3-4 人局 4/6、5-6 人局 5/7。
    · 新郎人选（p102）：优先持戒指的英雄；本项目无性别数据，"女性则
      最年长男性"退化为持戒者本身；无男性英雄的 NPC 分支未建模。
    · 英雄四步（每步每回合一次，顺序由 requires_flags 串起，p31）：
      ①知识 5+（卧室/餐厅/图书馆或持书）得知姓名 → ②知识 4+（地窖）
      定位 → ③力量 4+（地窖）起尸（尸体令牌自动背上）→ ④背尸与戒指
      进教堂。背尸入房按 2 格（movement_cost_multiplier）；尸体可转交
      （give_body），掉落时英雄进房自动拾起。
    · 新娘攻击（p102）：对非新郎正常精神伤害；对新郎转为力量流失
      （1-2→-1 / 3-4→-2 / 5+→-3），新郎力量耗尽即死亡（掉落戒指）。
      移动穿墙近似为正常寻路（已注明）。
    · 婚礼（p102）：新郎死后新娘由 bot 移进教堂即开婚；叛徒回合推进
      计时，第 3 回合婚礼完成 → 叛徒胜。
    · 英雄胜（p31）：尸体与戒指都在教堂（持戒指的英雄在场）→ 新娘
      安息。四步顺序保证流程，胜负判定只看最终状态。
    """

    mode = "ghost_bride"

    BRIDE = "ghost"
    CORPSE = "corpse"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        # p102：教堂与地窖强制入场
        engine._ensure_room_in_play("chapel", room_key)
        crypt_key = engine._ensure_room_in_play("crypt", room_key)
        chapel_key = next(
            (k for k, r in engine.state.board.items() if r.template_id == "chapel"),
            None,
        )
        flags["chapel_room"] = chapel_key
        # 新郎尸体放地窖
        if crypt_key:
            engine.spawn_token(self.CORPSE, label="新郎的尸体", role="marker", room_key=crypt_key)
        # 新娘在叛徒房间；3-4 人局 4/6，5-6 人局 5/7
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            spec = next(
                (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.BRIDE),
                {},
            )
            spec = dict(spec)
            if len(engine.state.players) >= 5:
                spec["speed"], spec["sanity"] = 5, 7
            bride = engine._spawn_single_haunt_monster(spec, traitor.room_key)
            if bride is not None:
                engine.spawn_token("bride", label="幽灵新娘", role="marker", room_key=traitor.room_key)
        # 新郎人选：优先持戒指的英雄（p102；性别数据缺失，退化见类注释）
        ring_holder = next(
            (p for p in engine.state.players if p.role == "hero" and "omen_ring" in p.items),
            None,
        )
        groom = ring_holder or next(
            (p for p in engine.state.players if p.role == "hero" and not p.dead),
            None,
        )
        if groom is not None:
            flags["groom_id"] = groom.id
            engine._log(f"幽灵新娘选定了她选定的新郎——{groom.name}！")
        engine._log("婚礼进行曲在房子里轻轻回响……")

    # ------------------------------------------------------------- 内部
    def _groom(self, engine: Any) -> Any | None:
        gid = engine._haunt_flags().get("groom_id")
        return next((p for p in engine.state.players if p.id == gid), None)

    def _chapel(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("chapel_room")

    # ------------------------------------------------------------- 移动
    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None) -> int:
        """p31：背着新郎尸体入房按 2 格移动计。"""
        if engine.tokens_held_by(player.id, self.CORPSE):
            return 2
        return 1

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        """尸体掉在地上时，英雄进房自动拾起。"""
        if player.role != "hero" or player.dead:
            return
        corpse = next(iter(engine.tokens_in_room(room.key, self.CORPSE)), None)
        if corpse is not None and engine._haunt_flags().get("body_disintered"):
            engine.give_token(corpse.uid, player.id)
            engine._log(f"{player.name} 扛起了新郎的尸体。")

    # ------------------------------------------------------------- 新娘
    def _groom_is_dead(self, engine: Any) -> bool:
        """新郎是否已死——按棋盘事实查询，而不是只认一次性事件标记。

        `groom_dead` 过去只在新娘的攻击杀死新郎那一处置位。新郎是英雄玩家，
        完全可能死于别的来源（英雄内斗、事件、其它怪物），那时婚礼线永远不
        触发：新娘继续追人、叛徒的胜利路线静默失效。这里按事实补正。
        """
        flags = engine._haunt_flags()
        if flags.get("groom_dead"):
            return True
        groom = self._groom(engine)
        if groom is not None and groom.dead:
            flags["groom_dead"] = True
            engine._log(f"{groom.name} 死了——他的魂魄被婚礼的誓言缚住了……")
            return True
        return False

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.BRIDE:
            return False
        flags = engine._haunt_flags()
        if self._groom_is_dead(engine):
            # 新郎已死：新娘去教堂开婚
            chapel = self._chapel(engine)
            if chapel:
                if monster.room_key != chapel:
                    monster.room_key = chapel
                    engine._log("新娘飘进了教堂——婚礼开始了！")
                if not flags.get("wedding_started"):
                    flags["wedding_started"] = True
                    engine._log("婚礼开始了——誓言将在第三回合完成。")
            return True
        groom = self._groom(engine)
        target = groom if (groom is not None and not groom.dead) else engine._find_monster_target(monster)
        if target is None:
            return True
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 4), "新娘移动")
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"新娘飘到了{engine.state.board[monster.room_key].name}。")
        return True

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.BRIDE:
            return False
        victims = [
            p for p in engine.state.players
            if not p.dead and p.room_key == monster.room_key
        ]
        if not victims:
            return True
        # 优先攻击新郎（p102：杀死新郎是叛徒的胜利路线）
        groom = self._groom(engine)
        victim = groom if (groom is not None and not groom.dead and groom.room_key == monster.room_key) else victims[0]
        bride_roll = engine._roll_monster_attack(monster, "sanity")
        hero_roll = engine._roll_attack(victim, "sanity")
        engine._log(f"新娘的目光刺入 {victim.name} 的脑海：{bride_roll} 对 {hero_roll}。")
        if bride_roll > hero_roll:
            amount = bride_roll - hero_roll
            if groom is not None and victim.id == groom.id:
                # p102：对 selected groom 的伤害转为力量流失（分档）
                loss = 1 if amount <= 2 else (2 if amount <= 4 else 3)
                engine._apply_stat_loss(victim, "might", loss)
                engine._log(f"{victim.name} 的生命力被抽走（力量 -{loss}）。")
                engine._check_player_death(victim)
                if victim.dead:
                    flags = engine._haunt_flags()
                    flags["groom_dead"] = True
                    engine._log(f"{victim.name} 死了——他的魂魄被婚礼的誓言缚住了……")
                    engine.check_victory()
            else:
                engine._deal_damage(victim, "mental", amount, source="幽灵新娘")
        elif bride_roll < hero_roll:
            engine._log(f"{victim.name} 挡住了新娘的凝视。")  # p102：新娘不可被晕
        return True

    # ------------------------------------------------------------- 行动
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "disinter_body":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine.last_haunt_action_succeeded():
                corpse = next(iter(engine.tokens_in_room(player.room_key, self.CORPSE)), None)
                if corpse is not None:
                    engine.give_token(corpse.uid, player.id)
                    engine._log(f"{player.name} 挖出了新郎的尸体，扛在肩上（入房按 2 格计）。")
            return ok
        if action_id == "give_body":
            target_id = (data or {}).get("target_id")
            target = next((p for p in engine.state.players if p.id == target_id), None)
            corpse = next(iter(engine.tokens_held_by(player.id, self.CORPSE)), None)
            if target is None or target.dead or target.room_key != player.room_key or corpse is None:
                engine._log("需要同房间的一名存活探险者来接手尸体。")
                return False
            engine.give_token(corpse.uid, target.id)
            engine._log(f"{player.name} 把尸体交给了 {target.name}。")
            return True
        return super().perform_action(engine, player, action_id, data)

    def on_player_died(self, engine: Any, player: Any) -> None:
        """p31：扛尸者倒下时尸体掉在原地——否则尸体悬在死人身上，英雄线断掉。

        seed137/5p 实测：扛尸英雄在地下墓穴阵亡，尸体令牌停在"被背着"状态
        （room_key 空、holder 是死人），教堂判定永远不成立，整局 400 回合
        收不了场。掉在原地后，后来者进房会自动扛起（见 on_enter_room）。
        """
        for token in engine.tokens_held_by(player.id, self.CORPSE):
            engine.place_token(token.uid, player.room_key)

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p31：按步骤走——问名 → 地窖定位/掘尸 → 把尸体与戒指送进小教堂。

        没有这条时机器人手里拿着关键牌也只会到处乱走（seed137/5p 实测 400 回合
        收不了场：剩下的英雄在图书馆/入口大厅/大楼梯之间兜圈子）。
        """
        if player.dead or player.role != "hero":
            return []
        flags = engine._haunt_flags()
        chapel = self._chapel(engine)
        if not flags.get("groom_name_known"):
            name_rooms = [
                f"__room__{key}"
                for key, room in engine.state.board.items()
                if room.template_id in ("bedroom", "dining_room", "library")
            ]
            # 找不到这三间就直接去教堂方向碰运气（书也可能在身上）
            return name_rooms or ([f"__room__{chapel}"] if chapel else [])
        corpse_held = bool(engine.tokens_held_by(player.id, self.CORPSE))
        ring_held = "omen_ring" in player.items
        if chapel and (corpse_held or ring_held):
            return [f"__room__{chapel}"]  # 扛尸/持戒的人直奔教堂
        if not flags.get("body_disintered"):
            crypt = next(
                (key for key, room in engine.state.board.items() if room.template_id == "crypt"),
                None,
            )
            return [f"__room__{crypt}"] if crypt else []
        return [f"__room__{chapel}"] if chapel else []  # 尸体已出土：去教堂集合

    # ------------------------------------------------------------- 婚礼计时
    def _timer_ticks_now(self, engine: Any, player: Any) -> bool:
        """计时器该由谁推进：叛徒活着就是叛徒；叛徒已死则由每个轮回的第一位
        存活玩家代跑——引擎的 start_turn 会跳过死者回合，新娘照常完婚，
        计时没人推的话叛徒胜线在叛徒死后就静默失效（seed137/5p 的 400 回合
        死局里 wedding_timer 就停在 0）。"""
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            return player.id == traitor.id
        for player_id in engine.state.turn_order:
            owner = next((p for p in engine.state.players if p.id == player_id), None)
            if owner is not None and not owner.dead:
                return owner.id == player.id
        return False

    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if not flags.get("wedding_started"):
            return
        if not self._timer_ticks_now(engine, player):
            return
        # p102：婚礼开始后每回合推进，第 3 回合完成
        current = int(engine._haunt_track_value("wedding_timer")) + 1
        engine._set_haunt_track_value("wedding_timer", current)
        engine._log(f"婚礼进行中……（{current}/3）")
        if current >= 3:
            engine._set_winner("traitor", "誓言已成——幽灵新娘与她的新郎永远结合了。")
            engine.check_victory()

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        chapel = self._chapel(engine)
        if chapel is not None and flags.get("body_disintered"):
            # 尸体可能被英雄背着（holder 模式）：持有者站在教堂也算"尸体在教堂"
            holder_ids = {p.id for p in engine.state.players if p.room_key == chapel and not p.dead}
            corpse_in_chapel = any(
                t.room_key == chapel or (t.holder is not None and t.holder in holder_ids)
                for t in engine.tokens_of_kind(self.CORPSE)
            )
            ring_in_chapel = any(
                p.role == "hero" and not p.dead and p.room_key == chapel and "omen_ring" in p.items
                for p in engine.state.players
            )
            if corpse_in_chapel and ring_in_chapel:
                engine._set_winner("heroes", "戒指戴上枯骨的手指——两道身影相携淡去，安息了。")
                return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "再没有人能打断这场婚礼了。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p31/p102 只认"戒指与尸骨在教堂"，
        # 叛徒死后幽灵新娘照常完婚。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
