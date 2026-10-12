"""CracklingAuraMode（剧本 52）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    HauntAction,
)


class CracklingAuraMode(GenericModeHandler):
    """剧本 52 噼啪光环中（In a Crackling Aura）。

    权威原文：英雄手册 p63 / 叛徒手册 p134。
    · Turn/Damage 轨起步 = 作祟开始时的英雄数；英雄「破解戒指」逐点打掉，
      归零则戒指失去全部魔力、戴着它的人昏迷（p63）。
    · 魔法尘：英雄在有事件图标的房间掷 3 骰（水晶球 4 骰）4+ → 获得一枚；
      可丢弃/交易/被偷，丢弃即在房间形成反魔法场；同一人手里的尘合并成
      一枚；带反魔法场的房间不能再搜尘。
    · 叛徒：+1 知识、固定 3 骰防守、受伤 −1、不能做常规攻击（只能施法），
      开局戴上戒指；在五芒星室放弃整回合召唤恶魔领主（知识 5+，
      Might 7 Speed 5 Sanity 4）；每回合开始清除自己与恶魔所在房间的反魔法场。
    · 英雄胜：戒指被破解 + 场上无恶魔；叛徒胜：英雄全灭。恶魔领主只能靠
      "知识 6+ 逆转召唤"或"持蜡烛/圣徽的理智攻击造成伤害"驱逐，硬打只能
      把它打晕（p63）。
    · 简化：传送法术（Blink/Return）未建模；"神秘硬币 +1 骰防法术"未建模
      （牌堆里没有这张牌，戴面具攻击叛徒 +1 骰由卡牌的 attack 加值通用覆盖）；
      "叛徒把物理伤害改为精神伤害"是玩家选择，交给数值结算按原样受物理伤害；
      叛徒死亡/戒指被偷时的身份互换未建模（戒指掉在房间里，英雄照常就地破解）。
    """

    mode = "ring_exorcism"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["anti_magic_rooms"] = []
        flags["demon_alive"] = False
        flags["ring_disenchanted"] = False
        flags["spell_fireball"] = False
        flags["spell_boiling_blood"] = False
        # p63/p134：Turn/Damage 轨起步 = 作祟开始时的英雄数，英雄靠"破解戒指"
        # 逐点打掉它；归零则戒指失效、佩戴者昏迷。旧实现整条胜线缺失（只有
        # "杀叛徒"这一条代办口径），实测两局 300 回合僵局：英雄每人囤 14-45 枚
        # 魔法尘却无事可做，叛徒也杀不完他们，双方谁也赢不了。
        heroes = sum(1 for p in engine.state.players if p.role == "hero")
        track = engine._haunt_tracks().setdefault(
            "ring_track",
            {"label": "戒指魔力（Turn/Damage 轨）", "target": heroes, "value": heroes},
        )
        track["target"] = heroes
        track["value"] = heroes
        # p134："You know the ring is special the moment you lay eyes on it…
        # When you put on the ring…"——戒指开局戴在叛徒手上（旧实现放任它留在
        # 抽到它的那个人手里，于是"与戒指同房破解"常常无从谈起）。
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            engine._grant_card_to_player(traitor, "omen_ring")
            # p134 叛徒手册 Right Now："Gain one Knowledge immediately."
            engine._heal_stat(traitor, "knowledge", 1)
        engine._log("你的朋友手上戴着一枚发光的戒指，周身噼啪作响……")

    # ------------------------------------------------------------- 状态查询
    def _ring_holder(self, engine):
        """身上带着戒指的玩家（p134：戒指不可主动交易/丢弃，只能被偷/拾取）。"""
        return next(
            (p for p in engine.state.players if not p.dead and "omen_ring" in p.items),
            None,
        )

    def _ring_room(self, engine):
        """戒指所在房间：有人佩戴即那间；叛徒倒下后戒指落在地上，也在那间。

        p63 的破解条件是"与戒指同房"，所以地板上的戒指同样可以被破解
        （且"戒指不在叛徒手上时攻击自动成功"）。
        """
        holder = self._ring_holder(engine)
        if holder is not None:
            return holder.room_key
        for room_key, items in engine.state.room_items.items():
            if "omen_ring" in items:
                return room_key
        return None

    def _demon(self, engine):
        return next(
            (m for m in engine.state.monsters if getattr(m, "name", "") == "恶魔领主"),
            None,
        )

    def on_turn_start(self, engine, player):
        """p134「Do This On Your Turn」：叛徒回合开始清除反魔法场。

        原文只清除"自己所在房间"与"恶魔所在房间"两处。旧实现把反魔法场做成
        永久的（"持续到被覆盖"），等于英雄丢一次尘就废掉叛徒整条召唤/施法线。
        """
        if player.dead or player.role != "traitor":
            return
        self._strip_anti_magic(engine, player.room_key)
        demon = self._demon(engine)
        if demon is not None:
            self._strip_anti_magic(engine, demon.room_key)

    def _strip_anti_magic(self, engine, room_key) -> bool:
        if not room_key:
            return False
        flags = engine._haunt_flags()
        anti = flags.setdefault("anti_magic_rooms", [])
        if room_key not in anti:
            return False
        anti.remove(room_key)
        for token in list(engine.tokens_in_room(room_key, "magic_dust")):
            engine.remove_token(token.uid)
        engine._log(f"{engine.state.board[room_key].name}的反魔法场被戒指的魔力冲散了。")
        return True

    def on_turn_end(self, engine, player):
        """p134：回合结束在特定房间习得法术；图书馆给叛徒补知识。"""
        if player.dead or player.role != "traitor":
            return
        flags = engine._haunt_flags()
        template = getattr(engine.current_room(player), "template_id", "")
        if template == "charred_room" and not flags.get("spell_fireball"):
            flags["spell_fireball"] = True
            engine._log(f"{player.name} 在烧焦的房间里领悟了火球术！")
        elif template == "bloody_room" and not flags.get("spell_boiling_blood"):
            flags["spell_boiling_blood"] = True
            engine._log(f"{player.name} 在血房间里领悟了沸血术！")
        if template == "library":
            start = int(self._starting_stats(engine, player).get("knowledge", 0))
            knowledge = int(player.stats.get("knowledge", 0))
            # p134 Library Bonus：知识 ≤ 起始值、或 < 4 时 +1（可超过起始值）。
            if knowledge <= start or knowledge < 4:
                engine._heal_stat(player, "knowledge", 1)
                engine._log("图书馆的典籍让叛徒的知识增长了 1 点。")

    def _starting_stats(self, engine, player) -> dict:
        """角色卡的起始属性（复原术与图书馆加成的上限口径）。"""
        face = engine.catalog.characters.get(player.character_id)
        return dict(getattr(face, "stats", {}) or {})

    def on_player_died(self, engine, player):
        """倒下者手里的魔法尘落到房间里。

        引擎的死亡处理只丢卡牌；尘是令牌，不落地就永远拿不回来（队友进房
        会自动捡起无主的 carried 令牌）。
        """
        if player.role != "hero":
            return
        for token in list(engine.tokens_held_by(player.id, "magic_dust")):
            engine.place_token(token.uid, player.room_key)
            room_name = engine.state.board[player.room_key].name if player.room_key in engine.state.board else "房间"
            engine._log(f"{player.name} 的魔法尘落在了{room_name}。")

    def on_monster_defeated(self, engine, monster, amount):
        """p63：只有"持蜡烛/圣徽做理智攻击并造成伤害"才驱逐恶魔领主。

        常规攻击按引擎惯例只是把怪物打晕（恶魔领主 Might 7，硬打几乎打不动
        ——这正是原文给英雄留的那条理智线）。知识 6+ 的逆转召唤走
        `_banish_demon`，不经这里。
        """
        if getattr(monster, "name", "") != "恶魔领主":
            return False
        if str(getattr(engine, "_last_attack_attr", "")) != "sanity":
            engine._log("常规攻击只能让恶魔领主踉跄一下——要驱逐它得用蜡烛或圣徽做理智攻击。")
            return False
        self._remove_demon(engine)
        return True

    def _remove_demon(self, engine) -> None:
        flags = engine._haunt_flags()
        demon = self._demon(engine)
        flags["demon_alive"] = False
        if demon is not None:
            monster_id = getattr(demon, "id", None)
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
            ]
        engine._log("恶魔领主被驱回了地狱！")
        engine.check_victory()

    def _is_sanity_banish(self, engine, attacker, target) -> bool:
        """p63：持蜡烛或圣徽、与恶魔领主同房间的英雄，可以用理智攻击它。"""
        if getattr(target, "name", "") != "恶魔领主":
            return False
        items = set(getattr(attacker, "items", ()) or ())
        return bool(items & {"item_candle", "omen_holy_symbol"})

    def _pentagram_key(self, engine):
        return next(
            (k for k, r in engine.state.board.items() if r.template_id == "pentagram_chamber"),
            None,
        )

    def _can_disenchant(self, engine, player) -> bool:
        """p63：与戒指同房、自己持魔法尘、且戒指还没被破解。

        戒指掉在地板上时也算"与戒指同房"——p63 说"戒指不在叛徒手上时攻击
        自动成功"，所以佩戴者倒下后英雄仍能就地破解（否则那局就是死局）。
        """
        flags = engine._haunt_flags()
        if flags.get("ring_disenchanted"):
            return False
        if not engine.tokens_held_by(player.id, "magic_dust"):
            return False
        return self._ring_room(engine) == player.room_key

    def _can_banish(self, engine, player, flags=None) -> bool:
        """p63：到恶魔被召唤的房间（五芒星室）做知识 6+ 逆转召唤。"""
        flags = flags if flags is not None else engine._haunt_flags()
        if not flags.get("demon_alive"):
            return False
        pentagram = self._pentagram_key(engine)
        return pentagram is not None and player.room_key == pentagram

    def _can_summon(self, engine, player, flags) -> bool:
        """p134：在五芒星室放弃整个回合作知识 5+ 的召唤；反魔法场里不行。"""
        if flags.get("demon_alive"):
            return False
        pentagram = self._pentagram_key(engine)
        if pentagram is None or player.room_key != pentagram:
            return False
        return pentagram not in flags.get("anti_magic_rooms", [])

    def _wounded_amount(self, engine, player) -> int:
        start = self._starting_stats(engine, player)
        return sum(
            max(0, int(start.get(stat, 0)) - int(player.stats.get(stat, 0)))
            for stat in ("might", "speed", "sanity", "knowledge")
        )

    def _enchant_targets(self, engine, player) -> list:
        """同房间的英雄里知识不低于其理智的那些：真人只在占优时才开打。"""
        knowledge = engine._effective_stat(player, "knowledge")
        return [
            other
            for other in engine.state.players
            if other.role == "hero"
            and not other.dead
            and other.room_key == player.room_key
            and engine._effective_stat(other, "sanity") <= knowledge
        ]

    def _fireball_rooms(self, engine, player) -> dict:
        """p134 火球术：视线内的相邻房间（可覆盖那间房里所有英雄）。"""
        if not engine._haunt_flags().get("spell_fireball"):
            return {}
        rooms: dict[str, list] = {}
        for option in engine.available_move_options(player):
            key = getattr(option, "target_key", "") or ""
            if not key or key not in engine.state.board:
                continue
            if not engine._has_line_of_sight(player.room_key, key):
                continue
            victims = [
                other
                for other in engine.state.players
                if other.role == "hero" and not other.dead and other.room_key == key
            ]
            if victims:
                rooms[key] = victims
        return rooms

    def _boiling_blood_targets(self, engine, player) -> list:
        """p134 沸血术：视线内一名英雄；优先挑理智最差的那个。"""
        if not engine._haunt_flags().get("spell_boiling_blood"):
            return []
        victims = [
            other
            for other in engine.state.players
            if other.role == "hero"
            and not other.dead
            and engine._has_line_of_sight(player.room_key, other.room_key)
        ]
        return sorted(victims, key=lambda item: engine._effective_stat(item, "sanity"))

    # ------------------------------------------------------------- 可用行动
    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        flags = engine._haunt_flags()
        if player.role == "traitor":
            return self._traitor_actions(engine, player, actions, flags)
        return self._hero_actions(engine, player, actions, flags)

    def _hero_actions(self, engine, player, actions, flags):
        can_disenchant = self._can_disenchant(engine, player)
        can_banish = self._can_banish(engine, player, flags)
        holding_dust = bool(engine.tokens_held_by(player.id, "magic_dust"))
        # p63："If a hero is ever holding more than one token of magic dust, the
        # dust magically combines into a single token."——手里已经有尘还去搜，
        # 搜到也是白搜（合并掉）。真人有尘就会去用掉，不会原地再搜。
        handover = self._can_hand_over_dust(engine, player) if holding_dust else False
        result = []
        for action in actions:
            if action.id == "search_dust":
                room = engine.current_room(player)
                if room.symbol != "event":
                    continue
                # p63：带反魔法场的房间不能再搜尘
                if player.room_key in flags.get("anti_magic_rooms", []):
                    continue
                if holding_dust:
                    continue
                # 站在戒指旁边又拿着尘：该做的是破解戒指（尝试也会把尘消耗掉），
                # 再去搜尘纯属浪费——而且 search_dust 在 rule_data 里排在前面、
                # 两者在机器人打分里同分，不挡住它就永远轮不到破解（实测两局
                # 300 回合僵局里英雄各囤 14-45 枚尘、一次都没尝试过破解）。
                if can_disenchant:
                    continue
            elif action.id == "drop_dust":
                # 丢下即消散成反魔法场，对叛徒施法几乎没有影响（它在自己回合
                # 开始就会清掉）；真正的用途是**把尘传给别人**——本实现里魔法尘
                # 不能交易，"丢下→队友进房捡起"是唯一的传递方式。所以只在
                # "同房有没拿尘的队友、而自己这会儿用不上（破解不了）"时提供。
                if not handover or can_disenchant:
                    continue
            elif action.id == "disenchant_ring":
                if not can_disenchant:
                    continue
            elif action.id == "banish_demon":
                if not can_banish:
                    continue
            result.append(action)
        if can_banish:
            # 恶魔在场且自己站在召唤室：先逆转召唤。恶魔一次 6-9 点物理伤害，
            # 它不死英雄就赢不了（p63 要求"戒指被破解 且 无恶魔"），优先级
            # 高于继续磨戒指。人类玩家的列表保持原序（两条路都摆着），
            # 机器人只留最优的那条，免得探针把"出现过没选用"算成空转。
            if getattr(player, "control", "bot") == "bot":
                result = [item for item in result if item.id == "banish_demon"]
        return result

    def _can_hand_over_dust(self, engine, player) -> bool:
        """同房间是否有"手里没尘的活英雄"可以接手这枚魔法尘。"""
        for other in engine.state.players:
            if other.id == player.id or other.dead or other.role != "hero":
                continue
            if other.room_key == player.room_key and not engine.tokens_held_by(
                other.id, "magic_dust"
            ):
                return True
        return False

    def _traitor_actions(self, engine, player, actions, flags):
        """叛徒的行动：召唤（放弃整回合）＋法术，按**期望收益**排序。

        列表顺序就是机器人同分时的取舍：召唤永远第一（唯一的取胜主线），
        其余法术按期望伤害/治疗量降序——真人也是挑"这一下最疼的那个"打，
        而不是永远先放同一个法术（实测 seed103/6p 里沸血术出现过 3 次却
        一次没用：附魔固定排在它前面，哪怕对手理智很高、附魔并不划算）。
        """
        named = {action.id: action for action in actions}
        result = []
        if self._can_summon(engine, player, flags):
            result.append(named.get("summon_demon") or HauntAction("summon_demon", "召唤恶魔领主"))
            if getattr(player, "control", "bot") == "bot":
                # 召唤要放弃整个回合，本就与法术互斥；机器人只留这一条
                # （真人看到全部）。seed109/4p 实测：两条并列时机器人选了
                # 召唤，附魔就成了探针口中的"出现过没选用"。
                return result
        knowledge = engine._effective_stat(player, "knowledge")
        scored: list[tuple[float, Any]] = []
        for target in self._enchant_targets(engine, player):
            # 对抗净期望：赢下多少伤害、输掉多少就吃多少反噬。
            expected = self._contest_net(knowledge, engine._effective_stat(target, "sanity"))
            scored.append(
                (
                    expected,
                    HauntAction(
                        "enchant",
                        f"附魔：{target.name}",
                        "知识攻击，对方用理智防守，伤害为精神。",
                        {"target": target.id},
                    ),
                )
            )
        for key, victims in self._fireball_rooms(engine, player).items():
            # 每个英雄各自掷速度 5+，失败吃 2 骰物理（均值 2 点）。
            expected = sum(
                2.0 * (1.0 - self._p_at_least(engine._effective_stat(victim, "speed"), 5))
                for victim in victims
            )
            names = "、".join(victim.name for victim in victims)
            scored.append(
                (
                    expected,
                    HauntAction(
                        "cast_fireball",
                        f"火球术：{engine.state.board[key].name}（{names}）",
                        "该房间所有英雄做速度 5+，失败受 2 骰物理伤害。",
                        {"room": key},
                    ),
                )
            )
        for target in self._boiling_blood_targets(engine, player):
            # 理智 4+ 顶住，失败吃 3 骰物理（均值 3 点）。
            expected = 3.0 * (1.0 - self._p_at_least(engine._effective_stat(target, "sanity"), 4))
            scored.append(
                (
                    expected,
                    HauntAction(
                        "cast_boiling_blood",
                        f"沸血术：{target.name}",
                        "该英雄做理智 4+，失败受 3 骰物理伤害。",
                        {"target": target.id},
                    ),
                )
            )
        wounded = self._wounded_amount(engine, player)
        heal = named.get("restoration") or HauntAction("restoration", "复原术")
        if wounded >= 3:
            # 伤重先自愈：复原术按掷点补属性，均值≈知识点数。
            scored.append((float(max(wounded, knowledge)), heal))
        elif wounded > 0:
            scored.append((1.0, heal))
        scored.sort(key=lambda item: -item[0])
        picked = [action for _, action in scored]
        if getattr(player, "control", "bot") == "bot" and len(picked) > 1:
            # 引擎每回合只允许一次剧本行动，所以给机器人的候选只留期望最高的
            # 那一条——留着明知不会选的选项，既没有意义，又会让"出现过却一次
            # 没用"占满复核报告（实测 seed109/4p：伤重时机器人选自愈，与它
            # 并列的附魔就成了空转告警）。人类玩家的列表原样保留，仍可自由选。
            picked = picked[:1]
        return result + picked

    # --------------------------------------------------------------- 期望值
    @staticmethod
    def _roll_distribution(dice: int) -> dict[int, float]:
        """d 枚 0/1/2 骰的和分布（骰面各 1/3）。"""
        dist: dict[int, float] = {0: 1.0}
        for _ in range(max(0, min(8, int(dice)))):
            nxt: dict[int, float] = {}
            for total, prob in dist.items():
                for face in (0, 1, 2):
                    nxt[total + face] = nxt.get(total + face, 0.0) + prob / 3.0
            dist = nxt
        return dist

    def _p_at_least(self, dice: int, target: int) -> float:
        return sum(prob for total, prob in self._roll_distribution(dice).items() if total >= target)

    def _contest_net(self, attack_dice: int, defend_dice: int) -> float:
        """对抗的净期望：E[max(0,攻−守)] − E[max(0,守−攻)]（正=攻击方占优）。"""
        attack = self._roll_distribution(attack_dice)
        defend = self._roll_distribution(defend_dice)
        return sum((a - d) * pa * pd for a, pa in attack.items() for d, pd in defend.items())

    def perform_action(self, engine, player, action_id, data):
        flags = engine._haunt_flags()
        if action_id == "search_dust":
            dice = 4 if "omen_crystal_ball" in player.items else 3
            roll = engine.roll_dice(dice, "魔法尘")
            if roll >= 4:
                # p63：同一英雄手里的多枚魔法尘会"magically combine into a single
                # token"——旧实现每次成功都新生成一枚（实测开局僵局里有人囤到 45 枚）。
                if engine.tokens_held_by(player.id, "magic_dust"):
                    engine._log(f"{player.name} 又找到一份魔法尘——它与手里那枚合成了一枚。")
                else:
                    engine.spawn_token("magic_dust", label="魔法尘", role="carried", holder=player.id)
                    engine._log(f"{player.name} 找到了魔法尘！（{roll}）")
            else:
                engine._log(f"{player.name} 没有找到魔法尘（{roll}）。")
            return True

        if action_id == "disenchant_ring":
            return self._disenchant(engine, player)

        if action_id == "banish_demon":
            return self._banish_demon(engine, player)

        if action_id == "summon_demon":
            return self._summon_demon(engine, player, flags)

        if action_id == "restoration":
            return self._restoration(engine, player)

        if action_id == "enchant":
            return self._enchant(engine, player, data)

        if action_id == "cast_fireball":
            return self._cast_fireball(engine, player, data)

        if action_id == "cast_boiling_blood":
            return self._cast_boiling_blood(engine, player, data)

        if action_id == "drop_dust":
            token = next(iter(engine.tokens_held_by(player.id, "magic_dust")), None)
            if token is None:
                return False
            engine.place_token(token.uid, player.room_key)
            anti = flags.setdefault("anti_magic_rooms", [])
            if player.room_key not in anti:
                anti.append(player.room_key)
            engine._log(f"魔法尘散布在{engine.state.board[player.room_key].name}——反魔法场形成了！")
            return True

        return super().perform_action(engine, player, action_id, data)

    def _disenchant(self, engine, player) -> bool:
        """p63：与戒指同房且持尘 → 尝试破解（**尝试即消耗**携带的魔法尘）。

        · 戒指在叛徒手上：对叛徒做**速度攻击**；成功不造成伤害，只把
          Turn/Damage 轨 −1（p134：叛徒固定 3 骰防守）。
        · 戒指不在叛徒手上（掉在地上、或被英雄捡走）：攻击自动成功。
        轨归零 → 戒指失去全部魔力、佩戴者昏迷；无恶魔在场即英雄胜。
        """
        flags = engine._haunt_flags()
        if not self._can_disenchant(engine, player):
            return False
        holder = self._ring_holder(engine)
        for token in list(engine.tokens_held_by(player.id, "magic_dust")):
            engine.remove_token(token.uid)
        success = True
        if holder is not None and holder.role == "traitor":
            hero_roll = engine._roll_attack(player, "speed")
            traitor_roll = engine.roll_dice(3, "戒指防守")
            success = hero_roll > traitor_roll
            engine._log(
                f"{player.name} 尝试破解戒指：速度 {hero_roll} 对叛徒 {traitor_roll}"
                f"（固定 3 骰防守）——{'成功了' if success else '被挡下'}。"
            )
        else:
            engine._log(f"{player.name} 把魔法尘按在戒指上——戒指没有反抗之力。")
        if not success:
            return True
        current = engine._haunt_track_value("ring_track") - 1
        engine._set_haunt_track_value("ring_track", current)
        if current <= 0:
            flags["ring_disenchanted"] = True
            if holder is not None and holder.role == "traitor":
                holder.dead = True
                engine._log("戒指失去了全部魔力——戴着它的人陷入了昏迷！")
            else:
                engine._log("戒指失去了全部魔力，噼啪作响的光环熄灭了。")
        else:
            engine._log(
                f"戒指的魔力被消磨了一分（{current}/"
                f"{engine._haunt_track_target('ring_track')}）。"
            )
        engine.check_victory()
        return True

    def _banish_demon(self, engine, player) -> bool:
        """p63：在恶魔被召唤的房间做知识 6+（持古书 +1 骰），成功即驱逐。"""
        flags = engine._haunt_flags()
        if not flags.get("demon_alive"):
            return False
        dice = engine._effective_stat(player, "knowledge") + (
            1 if "omen_book" in player.items else 0
        )
        roll = engine.roll_dice(max(1, dice), "逆转召唤")
        engine._log(f"逆转召唤：{player.name} 掷出 {roll}（目标 6+）。")
        if roll < 6:
            return True
        self._remove_demon(engine)
        return True

    # --------------------------------------------------------------- 叛徒法术
    def _summon_demon(self, engine, player, flags) -> bool:
        """p134：放弃整个回合，知识 5+ 召唤恶魔领主；失败可以下回合再试。

        "放弃整个回合"落在移动力清零上——引擎的"每回合一次剧本行动 / 一次
        攻击"已经把其余空间堵住，这里再把人钉在原地即可。
        """
        if not self._can_summon(engine, player, flags):
            return False
        player.steps_remaining = 0
        roll = engine.roll_dice(max(1, engine._effective_stat(player, "knowledge")), "召唤恶魔")
        if roll < 5:
            engine._log(f"{player.name} 的召唤仪式失败了（{roll}）。")
            return True
        haunt_rule = engine.state.haunt.rule_data or {}
        spec = next(
            (item for item in haunt_rule.get("monsters", []) if item.get("template_id") == "giant"),
            {},
        )
        spec = dict(spec)
        spec["name"] = "恶魔领主"
        monster = engine._spawn_single_haunt_monster(spec, player.room_key)
        if monster is not None:
            flags["demon_alive"] = True
            engine._log("恶魔领主从五芒星室中降临！")
        return True

    def _restoration(self, engine, player) -> bool:
        """p134 复原术：掷知识骰，把总量不超过点数的属性补回来（不超起始值）。"""
        roll = engine.roll_dice(max(1, engine._effective_stat(player, "knowledge")), "复原术")
        start = self._starting_stats(engine, player)
        remaining = roll
        healed: list[str] = []
        for stat in ("might", "speed", "sanity", "knowledge"):
            if remaining <= 0:
                break
            cap = int(start.get(stat, player.stats.get(stat, 0)))
            missing = min(remaining, max(0, cap - int(player.stats.get(stat, 0))))
            if missing <= 0:
                continue
            engine._heal_stat(player, stat, missing)
            remaining -= missing
            healed.append(f"{stat}+{missing}")
        detail = "、".join(healed) if healed else "没有可恢复的属性"
        engine._log(f"{player.name} 施展复原术（掷出 {roll}）：{detail}。")
        return True

    def _enchant(self, engine, player, data) -> bool:
        """p134 附魔：对同房间英雄做知识攻击（对方理智防守，伤害为精神）。

        "If you inflict 3 or more points of damage with this spell, you may
        steal an item from the target in addition to dealing this damage."
        """
        try:
            target_id = int(data.get("target", -1))
        except (TypeError, ValueError):
            return False
        target = next(
            (
                other
                for other in engine.state.players
                if other.id == target_id and not other.dead and other.room_key == player.room_key
            ),
            None,
        )
        if target is None:
            return False
        attack = engine._roll_attack(player, "knowledge")
        defense = engine._roll_attack(target, "sanity")
        engine._log(f"{player.name} 施展附魔：知识 {attack} 对 {target.name} 的理智 {defense}。")
        if attack > defense:
            diff = attack - defense
            engine._deal_damage(target, "mental", diff, source="附魔")
            if diff >= 3 and target.items:
                engine._steal_from_target(player, target)
            engine.check_victory()
        elif defense > attack:
            # 攻击落败的一方承受差值——p134 的法术攻击同样是"攻击"。
            # 叛徒受伤 −1 的规则会把这个差值削掉 1 点。
            engine._deal_damage(player, "mental", defense - attack, source="附魔反噬")
            engine.check_victory()
        else:
            engine._log("法术在两人之间消散了，谁也没有受伤。")
        return True

    def _cast_fireball(self, engine, player, data) -> bool:
        """p134 火球术：目标房间所有英雄做速度 5+，失败受 2 骰物理伤害。"""
        key = str(data.get("room", ""))
        victims = [
            other
            for other in engine.state.players
            if other.role == "hero" and not other.dead and other.room_key == key
        ]
        if not victims or key not in engine.state.board:
            return False
        engine._log(f"{player.name} 掷出火球——{engine.state.board[key].name}陷入火海！")
        for hero in victims:
            roll = engine.roll_dice(max(1, engine._effective_stat(hero, "speed")), "闪避火球")
            if roll >= 5:
                engine._log(f"{hero.name} 躲开了火球（{roll}）。")
                continue
            damage = engine.roll_damage_dice(2, "火球伤害")
            engine._log(f"{hero.name} 被火球击中（{roll}）。")
            engine._deal_damage(hero, "physical", damage, source="火球术")
        engine.check_victory()
        return True

    def _cast_boiling_blood(self, engine, player, data) -> bool:
        """p134 沸血术：视线内一名英雄做理智 4+，失败受 3 骰物理伤害。"""
        try:
            target_id = int(data.get("target", -1))
        except (TypeError, ValueError):
            return False
        target = next(
            (other for other in engine.state.players if other.id == target_id and not other.dead),
            None,
        )
        if target is None or not engine._has_line_of_sight(player.room_key, target.room_key):
            return False
        roll = engine.roll_dice(max(1, engine._effective_stat(target, "sanity")), "抵抗沸血")
        if roll >= 4:
            engine._log(f"{target.name} 顶住了沸血术（{roll}）。")
            return True
        damage = engine.roll_damage_dice(3, "沸血伤害")
        engine._log(f"{target.name} 的血液沸腾起来（{roll}）。")
        engine._deal_damage(target, "physical", damage, source="沸血术")
        engine.check_victory()
        return True

    # ------------------------------------------------------- 叛徒的规则修正
    def attack_allowed(self, engine, attacker, target) -> bool:
        """p134：叛徒不能做常规攻击、也不能使用武器——只能施法。"""
        return getattr(attacker, "role", "") != "traitor"

    def defense_roll_override(self, engine, attacker, target, weapon_card_id=None):
        """p134："If a hero attacks you, you always defend with 3 dice,
        regardless of your traits or the weapon used."（对英雄的攻击同理：
        英雄攻击叛徒时，叛徒以固定 3 骰防守。）"""
        if getattr(target, "role", "") != "traitor":
            return None
        roll = engine.roll_dice(3, "戒指防守")
        engine._log(f"{target.name} 以戒指之力固定 3 骰防守：{roll}。")
        return roll

    def physical_damage_reduction(self, engine, player, amount, source, damage_type) -> int:
        """p134："Whenever you take damage, the damage is reduced by 1."。"""
        if getattr(player, "role", "") != "traitor":
            return 0
        return 1

    def damage_reduction_label(self, engine, player) -> str:
        return "戒指的魔力"

    def attack_attr_override(self, engine, attacker, target, default_attr):
        """p63：持蜡烛或圣徽的英雄对恶魔领主改用理智攻击。

        引擎里没有"理智武器"这一类标签（蜡烛是知识武器、圣徽是预兆），
        所以这条规则只能落在属性覆盖钩子上——不实现它，原文给英雄留的
        那条驱逐路线（理智攻击造成任何伤害即驱逐）就永远打不出来。
        """
        if getattr(attacker, "role", "") == "traitor":
            return None
        return "sanity" if self._is_sanity_banish(engine, attacker, target) else None

    def attack_loss_damage_disabled(self, engine, attacker, target) -> bool:
        """p63："if not, you receive no damage"——理智驱逐失败不挨反击。"""
        return self._is_sanity_banish(engine, attacker, target)

    def check_victory(self, engine):
        flags = engine._haunt_flags()
        demons = [m for m in engine.state.monsters if getattr(m, "name", "") == "恶魔领主"]
        # p63："If the Turn/Damage Track reaches zero, the Ring is disenchanted…
        # If there is no demon in play, the heroes win."
        if flags.get("ring_disenchanted") and not demons:
            engine._set_winner("heroes", "戒指失去了魔力，房子里再没有恶魔——英雄们赢了。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "恶魔的嚎叫淹没了最后的呼救。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p63/p134 的胜利条件是"戒指被破解
        # **且** 无恶魔在场"。叛徒被打倒并不等于英雄胜（戒指会掉在房间里，
        # 英雄仍须就地把它破解掉），这一点旧实现（叛徒死＝英雄胜）正好反了。
        return True

    # ------------------------------------------------------------- bot 寻路
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p63：英雄胜 = 破解戒指（把 Turn/Damage 轨打光）+ 无恶魔在场。

        英雄：① 手里有魔法尘 → 去找戒指（佩戴者所在房间；戒指掉在地上就是
        那间房）；② 没尘 → 去有事件符号、且没有反魔法场的房间搜尘；
        ③ 戒指已破解而恶魔还在 → 去五芒星室逆转召唤。
        叛徒：召唤线由 rule_data 的 summon_demon.rooms 负责（五芒星室）；
        恶魔在场后再去烧焦的房间/血房间补法术——真人也这么干。
        """
        if player.dead:
            return []
        flags = engine._haunt_flags()
        if player.role == "traitor":
            if not flags.get("demon_alive"):
                return []
            for template_id, learned in (
                ("charred_room", "spell_fireball"),
                ("bloody_room", "spell_boiling_blood"),
            ):
                if flags.get(learned):
                    continue
                key = next(
                    (
                        room_key
                        for room_key, room in engine.state.board.items()
                        if room.template_id == template_id
                    ),
                    "",
                )
                if key:
                    return [f"__room__{key}"]
            return []
        if flags.get("demon_alive"):
            demon = self._demon(engine)
            # 持蜡烛/圣徽的英雄能"理智攻击驱逐"——真人的分工就是让这种人去
            # 缠住恶魔，其余人继续磨戒指（两条胜利线并行）。
            if demon is not None and self._is_sanity_banish(engine, player, demon):
                return [f"__room__{demon.room_key}"]
            pentagram = self._pentagram_key(engine)
            alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
            # 恶魔在场时两条线都要走：留两人继续磨戒指，其余人去五芒星室做
            # 知识 6+ 的逆转召唤。实战里全员都去磨戒指＝没人管恶魔，恶魔一次
            # 6-9 点物理伤害地把人逐个打死（seed109/6p：戒指已到 4/5 仍团灭）。
            if not flags.get("ring_disenchanted") and player in alive[:2]:
                ring_room = self._ring_room(engine)
                if ring_room and engine.tokens_held_by(player.id, "magic_dust"):
                    return [f"__room__{ring_room}"]
                return [
                    f"__room__{key}"
                    for key, room in engine.state.board.items()
                    if room.symbol == "event"
                    and key not in flags.get("anti_magic_rooms", [])
                ]
            return [f"__room__{pentagram}"] if pentagram else []
        if not flags.get("ring_disenchanted"):
            ring_room = self._ring_room(engine)
            if ring_room and engine.tokens_held_by(player.id, "magic_dust"):
                return [f"__room__{ring_room}"]
            return [
                f"__room__{key}"
                for key, room in engine.state.board.items()
                if room.symbol == "event"
                and key not in flags.get("anti_magic_rooms", [])
            ]
        return []

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        """p63：手里已经有尘、戒指还没被破解 → 该去找人了，别在事件房扎营。

        实测（seed101/109/127 三人局）：英雄在事件房搜到尘后，"本回合已用、
        下回合还能在这儿搜"让机器人每回合原地不动，300 回合里双方谁也不碰
        谁——真人有尘就会去追戒指。
        """
        if player.dead or player.role != "hero":
            return False
        flags = engine._haunt_flags()
        if flags.get("ring_disenchanted"):
            return False
        if self._can_disenchant(engine, player) or self._can_banish(engine, player, flags):
            return False
        return bool(engine.tokens_held_by(player.id, "magic_dust"))
