"""PhantomBombMode（剧本 16）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class PhantomBombMode(GenericModeHandler):
    """剧本 16 幻影的怀抱（The Phantom's Embrace）。

    权威原文：英雄手册 p27 / 叛徒手册 p98。

    · 幻影（ghost 模板承载，Speed 0 / Might 6 / Sanity 5）：不攻击只
      防御（on_monster_turn_attack 拦下引擎默认攻击、on_monster_move
      令其不移动）。它在下一个被发现的带符号地下室房间出现，同时放下
      女孩令牌与"到访标记"（p98 distinctive token），并**抑制该次抽牌**
      ——英雄"代替抽牌"必须攻击幻影（引擎 suppress_room_draw 钩子）。
    · 战斗（p27/p98）：英雄击败幻影 → 幻影死亡，英雄获女孩令牌，该
      房间成为"可拆弹房间"；幻影防御成功（英雄攻击落败）→ 英雄照常
      受反击伤害，幻影带着女孩逃走（两枚令牌移除），下次再出现。
    · 拆弹（p27）：女孩获救后，在击败幻影的房间做知识 7+（每回合一次）。
    · 逃脱（p27）：入口大厅开前门（知识/力量 6+，通用框架取高者）；
      门开后，抱女孩的英雄回合开始仍站在入口大厅即带她逃出——原文为
      群体逃跑，电子版简化为持女孩者出门（已注明）。
    · 炸弹（p98）：叛徒回合开始推进计时器并掷等量骰，掷出阈值以上房子
      爆炸（3 人 8+ / 4 人 7+ / 5 人 6+ / 6 人 5+）。原文"回合结束"用
      "下一回合开始"近似，时序等价。
    · 兜底落位（p98）：地下室翻不出新房间而幻影又不在场时，替叛徒"任选"
      一个没放过标记的地下室房间安置幻影与女孩（选离英雄最远的一间）。
      缺这条时幻影可能永远不现身（女孩拿不到 → 拆弹/逃脱都开不了）。
    · 胜负：拆弹或带女孩逃出 → 英雄胜；爆炸或英雄全灭 → 叛徒胜。
      叛徒阵亡后计时器不冻结——炸弹照走，由每个轮回的第一位存活玩家
      代跑（叛徒一死炸弹就停摆的话，英雄线再断就是死局）。
    · 已知简化：开成功门后"抽事件卡"步骤未建模；女孩不可被偷是天然
      满足（女孩是令牌不是卡）。
    """

    mode = "phantom_bomb"

    PHANTOM = "ghost"
    GIRL = "girl"
    MARK = "phantom_mark"
    BLOWUP_THRESHOLD = {3: 8, 4: 7, 5: 6, 6: 5}

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        # p98：持有女孩卡的探险者失去她（女孩卡与令牌一并 set aside）
        holder = next((p for p in engine.state.players if "omen_girl" in p.items), None)
        if holder is not None:
            holder.items.remove("omen_girl")
        for deck in engine.state.card_decks.values():
            if "omen_girl" in deck:
                deck.remove("omen_girl")
        for key in list(engine.state.room_items.keys()):
            if "omen_girl" in engine.state.room_items.get(key, []):
                engine.state.room_items[key].remove("omen_girl")
        engine.state.card_discards.setdefault("omen", []).append("omen_girl")
        engine._log("女孩的尖叫声戛然而止——她被藏进了这栋房子的某处。")

    # ------------------------------------------------------------- 出现
    def _phantom_in_play(self, engine: Any) -> bool:
        return any(
            m.template_id == self.PHANTOM and int(getattr(m, "stunned_turns", 0)) >= 0
            for m in engine.state.monsters
        )

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        flags = engine._haunt_flags()
        if room.floor != -1 or room.symbol not in ("event", "omen"):
            return
        if flags.get("girl_rescued") or self._phantom_in_play(engine):
            return
        spec = next(
            (s for s in (engine.state.haunt.rule_data or {}).get("monsters", [])
             if s.get("template_id") == self.PHANTOM),
            {},
        )
        monster = engine._spawn_single_haunt_monster(spec, room.key)
        if monster is None:
            return
        engine.spawn_token(self.GIRL, label="女孩", role="marker", room_key=room.key)
        engine.spawn_token(self.MARK, label="到访标记", role="marker", room_key=room.key)
        engine._log(
            f"{room.name}里，一个半透明的身影守着昏迷的女孩——他的幻影！先别管抽牌，攻击他！"
        )

    def suppress_room_draw(self, engine: Any, player: Any, room: Any) -> bool:
        """p27：幻影出现的房间，本次发现不抽符号牌（改为攻击幻影）。"""
        return any(m.room_key == room.key for m in engine.state.monsters if m.template_id == self.PHANTOM)

    # ------------------------------------------------------------- 行为
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.PHANTOM:
            return False
        return True  # p98：幻影不移动

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.PHANTOM:
            return False
        return True  # p98：幻影不攻击，只防御

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        """p27：幻影防御成功即带着女孩逃走；被击败则女孩获救。"""
        if _monster_id(target) != self.PHANTOM:
            return
        flags = engine._haunt_flags()
        phantom_id = getattr(target, "id", None)
        if attacker_won:
            flags["girl_rescued"] = True
            flags["bomb_room"] = target.room_key
            girl = next(iter(engine.tokens_in_room(target.room_key, self.GIRL)), None)
            if girl is not None:
                engine.give_token(girl.uid, attacker.id)
                flags["girl_holder_id"] = attacker.id
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != phantom_id
            ]
            engine._log(f"幻影消散了！{attacker.name} 抱起了女孩——房间里传来定时炸弹的滴答声……")
        else:
            # 防御成功 → 带女孩逃走（英雄已按常规吃了反击伤害）
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != phantom_id
            ]
            for t in list(engine.tokens_in_room(target.room_key, self.GIRL)):
                engine.remove_token(t.uid)
            engine._log("幻影抱起女孩化作一缕青烟逃走了——下一个带符号的地下室房间还会见到他。")

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        """获救的女孩掉在地上时，英雄进房自动抱起。"""
        flags = engine._haunt_flags()
        if player.role != "hero" or player.dead or not flags.get("girl_rescued"):
            return
        girl = next(iter(engine.tokens_in_room(room.key, self.GIRL)), None)
        if girl is not None:
            engine.give_token(girl.uid, player.id)
            flags["girl_holder_id"] = player.id
            engine._log(f"{player.name} 抱起了女孩。")

    # ------------------------------------------------------------- 逃脱 / 兜底
    def _entrance_key(self, engine: Any) -> str | None:
        return next(
            (key for key, room in engine.state.board.items() if room.template_id == "entrance_hall"),
            None,
        )

    def _place_phantom(self, engine: Any, room_key: str) -> None:
        spec = next(
            (s for s in (engine.state.haunt.rule_data or {}).get("monsters", [])
             if s.get("template_id") == self.PHANTOM),
            {},
        )
        if engine._spawn_single_haunt_monster(spec, room_key) is None:
            return
        engine.spawn_token(self.GIRL, label="女孩", role="marker", room_key=room_key)
        engine.spawn_token(self.MARK, label="到访标记", role="marker", room_key=room_key)

    def _fallback_placement(self, engine: Any) -> bool:
        """p98：地下室翻不出新房间时，替叛徒指定幻影与女孩的落点。

        原文："若整个地下室都已探索完毕、而幻影依然存活，就在怪物回合开始时
        任选一个地下室房间，宣布幻影和女孩身处哪个房间"；且"在每一个地下室
        房间都放有一枚有辨识度的令牌之前，幻影绝不会两次移动到同一个房间"。
        缺这条兜底时幻影可能永远等不到"下一个带符号的地下室房间"：女孩拿不到，
        拆弹与逃脱都开不了；叛徒再一死，炸弹没人推进，整局永远收不了场
        （seed137/4p 实测 400 回合：机器人3 在入口大厅↔地下室平台来回 544 次，
        `girl_rescued=False`、场上一只怪都没有）。
        """
        flags = engine._haunt_flags()
        if flags.get("girl_rescued") or self._phantom_in_play(engine):
            return False
        if engine.exploration_frontier_keys(-1):
            return False  # 地下层还能翻出新房间，先按"下一个带符号房间"走
        used = {key for key in engine.state.board if engine.tokens_in_room(key, self.MARK)}
        candidates: list[tuple[int, str]] = []
        for key, room in engine.state.board.items():
            if room.floor != -1 or key in used:
                continue
            distance = 0
            for hero in engine.state.players:
                if hero.role != "hero" or hero.dead:
                    continue
                length = engine._path_length(hero.room_key, key, avoid_transit=True)
                if length == 9999:
                    distance = -1
                    break
                distance = max(distance, length)
            if distance >= 0:
                candidates.append((distance, key))
        if not candidates:
            # 英雄哪间都走不到（极端布局）：别再挑三拣四，随便给一间保住胜线
            candidates = [
                (0, key) for key, room in engine.state.board.items()
                if room.floor == -1 and key not in used
            ]
        if not candidates:
            return False
        _distance, target = max(candidates)
        self._place_phantom(engine, target)
        engine._log(f"地下室的每个角落都被翻遍了——幻影抱着女孩现身在{engine.state.board[target].name}！")
        return True

    def _timer_ticks_now(self, engine: Any, player: Any) -> bool:
        """计时器该由谁推进：叛徒活着就是叛徒；叛徒已死则由每个轮回的第一位
        存活玩家代跑——引擎的 start_turn 会跳过死者回合，没人代跑的话炸弹永远
        停摆（见 _fallback_placement 里 seed137/4p 的死局）。"""
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            return player.id == traitor.id
        for player_id in engine.state.turn_order:
            owner = next((p for p in engine.state.players if p.id == player_id), None)
            if owner is not None and not owner.dead:
                return owner.id == player.id
        return False

    # ------------------------------------------------------------- 拆弹 / 逃生
    def _defuse_room_ok(self, engine: Any, player: Any) -> bool:
        """p27：拆弹只能在"击败幻影的那间房"做，且女孩必须已获救。"""
        flags = engine._haunt_flags()
        if not flags.get("girl_rescued") or flags.get("bomb_defused"):
            return False
        bomb_room = flags.get("bomb_room")
        return bomb_room is not None and player.room_key == bomb_room

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "defuse_bomb" and not self._defuse_room_ok(engine, player):
                continue  # 通用框架不认"击败幻影的房间"，这里补上 p27 的位置闸门
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "defuse_bomb" and not self._defuse_room_ok(engine, player):
            engine._log("必须回到击败幻影的那间房才能拆除炸弹。")
            return False
        return super().perform_action(engine, player, action_id, data)

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p27：抱女孩的去入口大厅开门脱身；其余人去找幻影/翻地下室/回房拆弹。

        没有这条时机器人没有剧本目标，在入口大厅↔地下室平台之间来回
        （seed137/4p 实测 544 次，整局 400 回合收不了场）。
        """
        if player.dead or player.role != "hero":
            return []
        flags = engine._haunt_flags()
        entrance = self._entrance_key(engine)
        if flags.get("girl_holder_id") == player.id and not flags.get("escaped"):
            return [f"__room__{entrance}"] if entrance else []
        phantom = next((m for m in engine.state.monsters if m.template_id == self.PHANTOM), None)
        if phantom is not None:
            return [f"__room__{phantom.room_key}"]  # 抢回女孩必须先打赢幻影
        if flags.get("girl_rescued"):
            bomb_room = flags.get("bomb_room")
            if bomb_room and not flags.get("bomb_defused"):
                return [f"__room__{bomb_room}"]
            return []
        # 幻影还没现身：去地下层还有空门位的房间继续翻牌（发现即现身）
        return [f"__room__{key}" for key in engine.exploration_frontier_keys(-1)]

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """幻影还没露面时，去翻新房间把它找出来（p27：它出现在"接下来发现的"
        带符号地下室房间）。

        缺这条时机器人只会在已有房间里转悠、不翻门：试玩实测 18 局里幻影
        0 次现身——女孩拿不到，拆弹与逃脱整条英雄线都开不了。
        """
        if player.dead or player.role != "hero":
            return False
        flags = engine._haunt_flags()
        if flags.get("girl_rescued") or flags.get("escaped") or flags.get("bomb_defused"):
            return False
        if self._phantom_in_play(engine):
            return False
        return bool(engine.exploration_frontier_keys(-1))

    # ------------------------------------------------------------- 回合开始
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        entrance = self._entrance_key(engine)
        if (
            player.role == "hero"
            and not player.dead
            and flags.get("front_door_open")
            and not flags.get("escaped")
            and flags.get("girl_holder_id") == player.id
            and entrance is not None
            and player.room_key == entrance
        ):
            # p27：门开了以后，抱着女孩站在入口大厅就从正门脱身
            flags["escaped"] = True
            engine._log(f"{player.name} 抱着女孩冲出了前门——身后的宅子还在滴答作响。")
            engine.check_victory()
            return
        self._fallback_placement(engine)
        if not self._timer_ticks_now(engine, player):
            return
        # p98：回合结束推进计时器——用"下一回合开始"近似
        track = int(engine._haunt_track_value("bomb_timer")) + 1
        engine._set_haunt_track_value("bomb_timer", track)
        threshold = self.BLOWUP_THRESHOLD.get(len(engine.state.players), 8)
        roll = engine.roll_dice(track, "炸弹计时")
        engine._log(f"滴答……计时器走到 {track}，掷出 {roll}（爆炸线 {threshold}+）。")
        if roll >= threshold:
            flags["house_blown"] = True
            engine._set_winner("traitor", "轰！！！房子炸上了天。")
            engine.check_victory()

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        if flags.get("house_blown"):
            return True  # winner 已在引信处设定
        if flags.get("bomb_defused"):
            engine._set_winner("heroes", "炸弹滴滴答答地哑了火——危机解除。")
            return True
        if flags.get("escaped"):
            engine._set_winner("heroes", "你抱着女孩逃出铁门——身后的宅邸还在滴答作响。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "没有一个英雄活着听到爆炸……或听到寂静。")
            return True
        return True  # 吸收引擎"叛徒死亡→英雄胜"：炸弹照走（_timer_ticks_now 代跑），胜负只认显式条件
