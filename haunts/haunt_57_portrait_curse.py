"""PortraitCurseMode（剧本 57）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class PortraitCurseMode(GenericModeHandler):
    """剧本 57「A Friend for the Ages」（英雄手册 p68 / 叛徒手册 p139）。

    三百年前一位挚友赠他的肖像成了抵御岁月与伤痛的护符：画在，人就不死。
    如今他咬定朋友们是来抢那幅画的——他们要毁掉它，还是替他守住它？

    · 颜料（p68）：令牌数 = 英雄数 + 2，只放阁楼/废弃房/坍塌房/露台/雕像走廊/
      储藏室（原版 Storeroom 与 Larder 在本项目共用 larder）/酒窖，每间一枚。
      房间比令牌多时，优先放"离任何探险者最远"的那几间；令牌比房间多时，
      多出来的先搁置，等清单上的房间被探索出来再补放（`on_room_discovered`）。
    · 画廊（p68）：肖像就挂在画廊。原版默认它在场，电子版探索阶段未必翻得到，
      开局用 `_ensure_room_in_play` 从房间牌堆把它找出来放下，否则英雄无处重绘。
    · 重绘（p68）：英雄在画廊且随身带着颜料 → 知识 4+ → 成功则颜料销毁并在
      房内放一枚知识检定令牌；检定令牌集满"作祟开始时的英雄数"即破除诅咒。
      目标数在 setup 里快照（`_resolve_haunt_target("hero_count")` 只数活人，
      英雄中途阵亡会让原版固定的目标缩水）。
    · 无敌（p139）：他的属性不受事件、房间特征与伤害削减。引擎所有伤害都走
      `_deal_damage` → `_adjust_damage_for_haunt`，所以 `physical_damage_reduction`
      对他全额减免即可；代价是他也不可能被击杀。英雄净胜 2 点仍能抢他一件
      物品（走引擎常规偷窃分支）。唯一例外：持远古护身符的英雄打赢他，
      伤害照常扣属性（p68）。
    · 肖像（p139）：他不得直视自己的画像——进入画廊、或回合开始就在画廊 →
      理智 4+，失败吃 1 骰精神伤害。这是唯一无视其免疫的伤害，用
      `_apply_damage_amounts` 直接结算绕开减免钩子；他也只可能死在这里，
      而"叛徒死亡"正是 p68 给英雄的第二条胜利路线。
    · 开局（p139）：先把低于起点的属性补回起点，再"每名英雄一次"把
      离起点滑格数最少的属性往上抬一格（并列时原版由玩家自选，这里按固定
      属性序取第一格保证同种子确定性）。
    · 销毁颜料（p139）：手持颜料时可以销毁一枚**代替一次攻击**——所以销毁后
      本回合不能再出刀（`attack_allowed`），且已攻击后不能再销毁。毁满 3 枚即胜。
    · 胜负（p68/p139）：英雄胜 = 集满知识检定令牌，或叛徒死亡；叛徒胜 =
      销毁 3 枚颜料，或英雄全灭。其中"叛徒死亡→英雄胜"由 handler 显式接管，
      "英雄全灭→叛徒胜"仍走引擎通用规则。

    已知简化：
        · "颜料不能被狗携带"自动满足——本项目同伴卡不占物品栏、无法持物。
        · 事件/房间特征中不走伤害结算的直接降属性（如 `event_the_voice`
          检定失败 -1 知识）没有被免疫拦住：引擎没有降属性钩子。
        · 抢颜料的阈值沿用引擎 `special_steal` 的"净胜 > 2"，比原版"净胜 ≥ 2"
          严一格；卡牌类物品的抢夺仍走引擎原分支。
        · 拿/传/放颜料与重绘共用引擎"每人每回合一次剧本行动"的限额。
        · "放下颜料 / 交给队友"只在同屋有空手且知识更高的英雄、且自己不在画廊时
          提供（原版颜料可像物品一样随处放下）。收窄的原因：机器人实测会陷入
          "放下→再捡起"的原地循环，一罐也带不进画廊。
        · 重绘的检定目标固定为知识 4+，不使用"多名英雄合力"之类的房规。
    """

    mode = "portrait_curse"

    PAINT = "paint"
    CHECK = "knowledge_check"
    GALLERY = "gallery"
    AMULET = "item_amulet_of_the_ages"
    PAINT_ROOMS = (
        "attic", "abandoned_room", "collapsed_room", "patio",
        "statuary_corridor", "larder", "wine_cellar",
    )
    STAT_ORDER = ("speed", "might", "sanity", "knowledge")

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p68：英雄胜利条件之二 = 叛徒死亡（"…or the Traitor is dead."）。
        # 显式接管判定，不再依赖引擎「叛徒死亡→英雄胜」的通用兜底。
        if heroes_alive and not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            engine._set_winner("heroes", "肖像的力量彻底熄灭了——它再也护不住任何人。")
            return True
        return super().check_victory(engine)

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        hero_count = max(1, sum(1 for p in engine.state.players if p.role == "hero" and not p.dead))
        flags["repaint_needed"] = hero_count
        flags["spell_broken"] = False
        flags["destroyed_this_turn"] = False
        tracks = engine._haunt_tracks()
        tracks.setdefault("repaint", {"label": "英雄：重绘肖像（知识检定令牌）", "target": hero_count, "value": 0})
        tracks["repaint"]["target"] = hero_count

        # p68：画廊是诅咒的所在，牌堆里找出来放下
        gallery_key = engine._ensure_room_in_play(self.GALLERY, room_key)
        if gallery_key:
            engine._log(f"那幅画就挂在{engine.state.board[gallery_key].name}——叛徒不敢看它第二眼。")
        else:
            engine._log("画廊没能放进屋子：英雄只能靠杀死叛徒来结束这一切（已知简化）。")

        total = hero_count + 2
        flags["paint_total"] = total
        placed = self._place_paint(engine, total)
        # p68 假设这些房间总能在屋里找到；本局可能一间都没翻到（实测 seed=109/4p
        # 零间、五罐颜料全被搁置），那样英雄一罐颜料都拿不到，重绘路线直接死锁。
        # 按 p84 的先例（"If the Pentagram Chamber isn't in the house, search the
        # room stack for it and put it…"）把清单上的房间强行拉进屋子，至少补足
        # 重绘所需的"英雄数"那一档；多出来的两罐仍走"搁置待发现"。
        while placed < hero_count:
            room_id = next(
                (
                    tid for tid in self.PAINT_ROOMS
                    if tid in (*engine.state.room_deck, *engine.state.room_discard)
                    and not any(room.template_id == tid for room in engine.state.board.values())
                ),
                None,
            )
            if room_id is None:
                break
            key = engine._ensure_room_in_play(room_id, room_key)
            if key is None:
                break  # 放不下（牌已还回牌堆）：再试别的房间只会死循环
            engine.spawn_token(self.PAINT, label="颜料", role="marker", room_key=key)
            placed += 1
        flags["pending_paint"] = max(0, total - placed)
        engine._log(
            f"{placed} 罐颜料散落在屋里最冷清的角落"
            + (f"，另有 {flags['pending_paint']} 罐等着房间被翻开。" if flags["pending_paint"] else "。")
        )
        self._boost_traitor(engine)

    def _place_paint(self, engine: Any, total: int) -> int:
        """p68：每间合适房一枚；房间比令牌多时挑离探险者最远的几间。"""
        candidates = [
            key for key, room in sorted(engine.state.board.items())
            if room.template_id in self.PAINT_ROOMS and not engine.tokens_in_room(key, self.PAINT)
        ]
        if not candidates:
            return 0
        if len(candidates) > total:
            candidates.sort(key=lambda key: (-self._min_distance_to_explorer(engine, key), key))
            candidates = candidates[:total]
        for key in candidates:
            engine.spawn_token(self.PAINT, label="颜料", role="marker", room_key=key)
        return len(candidates)

    def _min_distance_to_explorer(self, engine: Any, room_key: str) -> int:
        """该房间到"最近的活人"的距离（不可达记 0，不参与最远排序）。"""
        distances = [
            engine._path_length(room_key, player.room_key)
            for player in engine.state.players
            if not player.dead and player.room_key
        ]
        if not distances:
            return 0
        nearest = min(distances)
        return 0 if nearest >= 9999 else nearest

    def _boost_traitor(self, engine: Any) -> None:
        """p139：补回起点，然后每名英雄让他抬一格离起点最近的属性。"""
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is None or traitor.dead:
            return
        face = engine.catalog.characters.get(traitor.character_id)
        if face is None:
            return
        for stat in self.STAT_ORDER:
            start = face.stats.get(stat)
            track = engine._stat_track(traitor, stat)
            if start is None or not track:
                continue
            start_pos = next((i for i, value in enumerate(track) if value >= start), len(track) - 1)
            if traitor.stat_positions.get(stat, start_pos) < start_pos:
                traitor.stat_positions[stat] = start_pos
                traitor.stats[stat] = track[start_pos]
        hero_count = sum(1 for p in engine.state.players if p.role == "hero" and not p.dead)
        for _ in range(hero_count):
            best_stat = None
            best_gap = None
            for stat in self.STAT_ORDER:
                track = engine._stat_track(traitor, stat)
                if not track:
                    continue
                start = face.stats.get(stat)
                if start is None:
                    continue
                start_pos = next((i for i, value in enumerate(track) if value >= start), len(track) - 1)
                pos = traitor.stat_positions.get(stat, start_pos)
                gap = pos - start_pos  # 滑格高出起点几格（原版：least slider positions above start）
                if pos >= len(track) - 1:
                    continue  # 已到顶格，抬无可抬
                if best_gap is None or gap < best_gap:
                    best_stat, best_gap = stat, gap
            if best_stat is None:
                break
            pos = traitor.stat_positions[best_stat] + 1
            track = engine._stat_track(traitor, best_stat)
            traitor.stat_positions[best_stat] = min(pos, len(track) - 1)
            traitor.stats[best_stat] = track[traitor.stat_positions[best_stat]]
        engine._log(f"{traitor.name} 把岁月与伤口都移进了画里——他的属性高出起点一截。")

    # ------------------------------------------------------- 颜料与肖像
    def _held_paint(self, engine: Any, player: Any) -> list[Any]:
        return engine.tokens_held_by(player.id, self.PAINT)

    def _gallery_key(self, engine: Any) -> str:
        return next((key for key, room in engine.state.board.items() if room.template_id == self.GALLERY), "")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        """p68：搁置的颜料在清单上的房间被发现时补进去。"""
        flags = engine._haunt_flags()
        pending = int(flags.get("pending_paint", 0))
        if pending <= 0 or room.template_id not in self.PAINT_ROOMS:
            return
        if engine.tokens_in_room(room.key, self.PAINT):
            return
        flags["pending_paint"] = pending - 1
        engine.spawn_token(self.PAINT, label="颜料", role="marker", room_key=room.key)
        engine._log(f"{room.name}里另有一罐颜料（待放 {flags['pending_paint']} 罐）。")

    def _portrait_gaze(self, engine: Any, player: Any) -> None:
        """p139：叛徒进画廊/开局在画廊 → 理智 4+，失败吃 1 骰精神伤害（无视免疫）。"""
        if player.role != "traitor" or player.dead:
            return
        if engine._resolve_check(player, "sanity", 4, "抗拒肖像的凝视"):
            engine._log(f"{player.name} 强迫自己别去看那幅画。")
            return
        roll = engine.roll_dice(1, "肖像的反噬")
        engine._log(f"画中人替他挡下了三百年的伤，此刻却向他讨债（精神伤害 {roll}）。")
        # 直接结算：绕开 _deal_damage，否则会被他自己的免疫吃干净
        engine._apply_damage_amounts(player, mental=roll, source="肖像")
        engine.check_victory()

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        if room.template_id == self.GALLERY:
            self._portrait_gaze(engine, player)

    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.role == "traitor":
            flags["destroyed_this_turn"] = False
            if self._in_gallery(engine, player):
                self._portrait_gaze(engine, player)

    # --------------------------------------------------------- 无敌与抢夺
    def physical_damage_reduction(self, engine: Any, player: Any, amount: int, source: str, damage_type: str) -> int:
        """p139/p68：叛徒不受伤害削减；持远古护身符的英雄肉搏打赢他是唯一例外。"""
        if player.role != "traitor" or amount <= 0:
            return 0
        active_id = getattr(engine, "_active_player_id", None)
        attacker = None
        if active_id is not None and 0 <= active_id < len(engine.state.players):
            attacker = engine.state.players[active_id]
        if (
            source == "攻击"
            and attacker is not None
            and getattr(attacker, "role", "") == "hero"
            and self.AMULET in getattr(attacker, "items", [])
        ):
            return 0
        return amount

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p139：销毁颜料"代替一次攻击"——两件事一回合里只能做一件。"""
        if attacker.role != "traitor":
            return True
        return not bool(engine._haunt_flags().get("destroyed_this_turn"))

    def special_steal(self, engine: Any, attacker: Any, target: Any, diff: int, attack_attr: str) -> bool:
        """p68：颜料能像普通物品一样被抢走——他手里的颜料可以被夺下来。"""
        if target.role != "traitor" or getattr(attacker, "role", "") != "hero":
            return False
        held = self._held_paint(engine, target)
        if not held or self._held_paint(engine, attacker):
            return False  # 攻击者已带一枚，抢了也带不走
        token = held[0]
        engine.give_token(token.uid, attacker.id)
        engine._log(f"{attacker.name} 从{target.name}手里夺下了{token.label}！")
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        held = self._held_paint(engine, player)
        result = []
        for action in actions:
            action_id = action.id
            if action_id == "take_paint":
                if held or not engine.tokens_in_room(player.room_key, self.PAINT):
                    continue  # p68：每人同时只能携带一枚
            elif action_id == "repaint_portrait":
                # rooms 不写在 rule_data 里（会被 bot 当成常驻目标），限制由这里把关
                if not held or not self._in_gallery(engine, player):
                    continue
            elif action_id in {"drop_paint", "pass_paint", "destroy_paint"}:
                if not held:
                    continue
                if action_id == "destroy_paint":
                    if player.role != "traitor" or getattr(player, "attack_used", False):
                        continue  # 已经攻击过就不能再"代替攻击"
                elif self._in_gallery(engine, player) and self._can_make_check(
                    engine, player, "knowledge", 4
                ):
                    # 人都到画廊了且掷得出 4+，那就落笔，别再倒手颜料
                    continue
                elif not self._pass_targets(engine, player):
                    # 没人接得住就别放下：机器人只会"放下→再捡起"原地打转，
                    # 永远走不到画廊（实测 seed=109/4p 重绘 0/3）。
                    continue
            result.append(action)
        return result

    def _in_gallery(self, engine: Any, player: Any) -> bool:
        room = engine.state.board.get(player.room_key)
        return room is not None and room.template_id == self.GALLERY

    def _can_make_check(self, engine: Any, player: Any, stat: str, target: int) -> bool:
        """Betrayal 骰子面值 0/1/2，骰数 ×2 仍 < 目标就永远掷不出。"""
        try:
            dice = int(engine._effective_stat(player, stat)) + int(engine._check_bonus(player, stat))
        except Exception:
            dice = int((player.stats or {}).get(stat, 0) or 0)
        return max(1, min(8, dice)) * 2 >= int(target)

    def _pass_targets(self, engine: Any, player: Any) -> list[Any]:
        """同房、没带颜料的英雄（p68：颜料可以交易）。

        自己掷得出 4+ 时只交给知识更高的队友；自己永远掷不出时交给任何能画的
        空手队友——否则低知识的人抱着颜料在画廊空点到死。
        """
        if player.role != "hero":
            return []
        mine = int(player.stats.get("knowledge", 0))
        can_paint = self._can_make_check(engine, player, "knowledge", 4)
        result = []
        for other in engine.state.players:
            if (
                other.dead or other.id == player.id or other.role != "hero"
                or other.room_key != player.room_key or self._held_paint(engine, other)
            ):
                continue
            if can_paint and int(other.stats.get("knowledge", 0)) <= mine:
                continue
            if not can_paint and not self._can_make_check(engine, other, "knowledge", 4):
                continue
            result.append(other)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        held = self._held_paint(engine, player)
        if action_id == "take_paint":
            token = next(iter(engine.tokens_in_room(player.room_key, self.PAINT)), None)
            if token is None:
                engine._log("这个房间里没有颜料。")
                return False
            if held:
                engine._log("每人一次只能携带一罐颜料（p68）。")
                return False
            engine.give_token(token.uid, player.id)
            engine._log(f"{player.name} 收起了{token.label}。")
            return True

        if action_id == "drop_paint":
            if not held:
                engine._log("你身上没有颜料。")
                return False
            engine.place_token(held[0].uid, player.room_key)
            room = engine.state.board.get(player.room_key)
            engine._log(f"{player.name} 把颜料留在了{(room.name if room else '原地')}。")
            return True

        if action_id == "pass_paint":
            if not held:
                engine._log("你身上没有颜料可交。")
                return False
            candidates = self._pass_targets(engine, player)
            if not candidates:
                engine._log("同房间里没有需要颜料的队友。")
                return False
            choice = engine.prompter.choose_from_list(
                "传递颜料", "把颜料交给谁？", [p.name for p in candidates]
            )
            target = candidates[choice] if choice is not None and 0 <= choice < len(candidates) else candidates[0]
            engine.give_token(held[0].uid, target.id)
            engine._log(f"{player.name} 把颜料塞给了{target.name}。")
            return True

        if action_id == "repaint_portrait":
            if not held:
                engine._log("重绘肖像得先带上一罐颜料。")
                return False
            if not self._in_gallery(engine, player):
                engine._log("那幅画挂在画廊——重绘必须站在它面前（p68）。")
                return False
            before = engine._haunt_track_value("repaint")
            ran = super().perform_action(engine, player, action_id, data)
            # _perform_generic_haunt_action 只要执行就返回 True，成败要看轨道是否推进
            succeeded = ran and engine._haunt_track_value("repaint") > before
            if succeeded:
                engine.remove_token(held[0].uid)
                engine.spawn_token(self.CHECK, label="知识检定", role="marker", room_key=player.room_key)
                value = engine._haunt_track_value("repaint")
                goal = engine._haunt_track_target("repaint")
                stroke = "落下了最后一笔" if value >= goal else "又落下一笔"
                engine._log(f"{player.name} {stroke}（{value}/{goal}）——颜料用尽了。")
                if value >= goal:
                    engine._haunt_flags()["spell_broken"] = True
                    engine._log("肖像忽然变得陌生：画中人正在老去，而它守了三百年的东西正在流失。")
            return ran

        if action_id == "destroy_paint":
            if player.role != "traitor" or not held:
                engine._log("你手上没有颜料。")
                return False
            if getattr(player, "attack_used", False):
                engine._log("销毁颜料要代替本回合的攻击——你已经出过手了。")
                return False
            engine.remove_token(held[0].uid)
            value = engine._advance_haunt_track("paint_destroyed", 1)
            engine._haunt_flags()["destroyed_this_turn"] = True
            engine._log(f"{player.name} 把{held[0].label}捻成了碎片（已毁 {value}/3）。")
            engine.check_victory()
            return True

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 进度
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        paints = engine.tokens_of_kind(self.PAINT)
        lines = [
            f"颜料：房内 {sum(1 for t in paints if t.room_key)} 罐 / "
            f"随身 {sum(1 for t in paints if t.holder is not None)} 罐 / "
            f"已毁 {engine._haunt_track_value('paint_destroyed')}"
            f"/{engine._haunt_track_target('paint_destroyed')}",
            f"重绘：{engine._haunt_track_value('repaint')}/{engine._haunt_track_target('repaint')} 枚知识检定令牌",
        ]
        if int(flags.get("pending_paint", 0)) > 0:
            lines.append(f"还有 {flags['pending_paint']} 罐颜料等着房间被翻开")
        if self._gallery_key(engine):
            lines.append("肖像在画廊——叛徒不敢直视它")
        return lines

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """放下颜料只给人类；掷不出 4+ 就别在画廊空点重绘。"""
        if action_id == "drop_paint":
            return True
        if action_id == "repaint_portrait":
            return not self._can_make_check(engine, player, "knowledge", 4)
        return False

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        """掷不出 4+ 时别被「下回合还能重绘」钉在画廊。"""
        if player.dead or player.role != "hero":
            return False
        if self._held_paint(engine, player) and self._in_gallery(engine, player):
            return not self._can_make_check(engine, player, "knowledge", 4)
        return not self._in_gallery(engine, player) if self._held_paint(engine, player) else False

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """手里有颜料就往画廊跑，没有就去搜颜料；叛徒同样追颜料（好把它毁掉）。

        自己永远掷不出知识 4+ 时，去找能画的空手队友，而不是抱着罐子在画廊过夜。
        """
        if player.dead:
            return []
        if self._held_paint(engine, player):
            if player.role == "hero" and not self._can_make_check(engine, player, "knowledge", 4):
                mates = [
                    other
                    for other in engine.state.players
                    if other.role == "hero"
                    and not other.dead
                    and other.id != player.id
                    and not self._held_paint(engine, other)
                    and self._can_make_check(engine, other, "knowledge", 4)
                    and other.room_key
                ]
                if mates:
                    return [f"__room__{mates[0].room_key}"]
            gallery = self._gallery_key(engine)
            return [f"__room__{gallery}"] if gallery else []
        return [
            f"__room__{token.room_key}"
            for token in engine.tokens_of_kind(self.PAINT) if token.room_key
        ]
