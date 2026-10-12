"""NightfallMode（剧本 58）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class NightfallMode(GenericModeHandler):
    """剧本 58「Nightfall / 夜幕降临」（英雄手册 p69 / 叛徒手册 p140）。

    叛徒盼到了他的时刻：夜幕落下，整栋房子沉进一片自我主张的暮色里。
    暮色中人的身体不听使唤，只有心智还算锐利——想活下去，就去熔炉房
    点一支火把，然后一层一层把暮色赶出去。

    · 开局（p69/p140）：若熔炉房不在场则从房间牌堆取出放好（引擎
      `_ensure_room_in_play`，3/28 号同款先例；原文要求放地下室）；
      噩梦（Speed 2 / Might 2 / Knowledge 5 / Sanity 4）= 英雄数，
      铺在**带事件图标且离最近英雄 ≥4 格**的房间，不够远就取尽可能远的。
    · 暮色（p69/p140）：除熔炉房/花园/墓地/天井/阳台/塔楼之外的房间都在
      暮色里；叛徒所在房间**永远是暮色**（即使叛徒已死）；已驱散的楼层
      与有火把的房间不算暮色。
    · 火把（p69）：英雄在熔炉房可造火把代替攻击；火把抵消同房间的暮色，
      持火把者永不受暮色影响（按正常速度移动、正常力量攻击）。例外：
      叛徒与火把同房时只有持火把者受保护（已按原文实现）。
    · 消灭噩梦（p69）：受 2 点以上伤害即被摧毁移出游戏，更少则只是击晕。
    · 驱散暮色（p69）：同房间多名英雄且至少一人持火把时，由一人发起，
      同房所有活着的英雄各做一次知识 4+ 或理智 4+（做检定的英雄本回合
      不能移动/攻击）；**至少一个知识成功 + 一个理智成功** → 该层暮色
      被驱散；三层全驱散 → 英雄胜。
    · 缠梦（p140）：噩梦造成 ≥2 点精神伤害时可选择缠住该英雄（bot 总是
      选择缠梦）；被缠的英雄回合开始做理智 5+ 挣脱：成功则噩梦现身于
      英雄房间、失败则受 1 骰精神伤害。缠梦中的噩梦不行动、不可被攻击。
    · 暮色战斗（p69/p140）：暮色中不能做力量/速度攻击，但可用**知识攻击**
      （目标以知识防御、精神伤害）——attack_attr_override 覆盖；持火把
      者不受此限。
    · 胜负（p69/p140）：英雄胜 = 消灭所有噩梦，或三层暮色全部驱散；
      叛徒胜 = 英雄全灭。叛徒出局时噩梦照常行动，吸收兜底（7/8 号口径）。

    已知简化：
        · "暮色中用 Sanity 代替 Speed 决定移动力"未建模——引擎没有改移动
          力属性的钩子（只有 movement_cost_multiplier/floor），错误建模比
          不建模更糟，故只保留"暮色中改用知识攻击"这一条战斗影响。
        · "有朝外窗户的房间不在暮色中"未建模——内容库没有朝外窗标记。
        · 暮色中禁用斧/矛/血匕首/左轮、左轮不能射入暮色房、蜡烛/德鲁伊
          护符/水晶球作为知识武器的加骰，均未在物品系统层拦截。
        · 噩梦摧毁阈值：物理 ≥2 正确；精神伤害按统一阈值 2（原文 3，
          on_monster_defeated 钩子不提供伤害类型，无法区分）。
        · 缠梦英雄"被叛徒操控本回合"未建模（bot 无法代打）。
        · 驱散暮色的集体检定由发起者一次结算（原版各自声明本回合尝试）。
    """

    mode = "nightfall_twilight"

    NIGHTMARE = "nightmare"
    FURNACE = "furnace_room"
    CANDLE = "omen_candle"
    # p69：这些房间永远不在暮色中（朝外窗房间未建模）
    TWILIGHT_FREE = ("furnace_room", "garden", "graveyard", "patio", "balcony", "tower")
    FLOORS = (-1, 0, 1)
    BANISH_TARGET = 4

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("banished_floors", [])
        flags.setdefault("torches", {})
        flags.setdefault("haunting", {})

        # p69：熔炉房不在场就放进场（原版要求放地下室）
        furnace = engine._ensure_room_in_play(self.FURNACE, room_key)
        flags["furnace_key"] = furnace

        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.NIGHTMARE, {"template_id": self.NIGHTMARE, "name": "噩梦"})
        )
        for target in self._nightmare_rooms(engine, hero_count, room_key):
            engine._spawn_single_haunt_monster(spec, target)
        engine._log("屋里的声音一点点熄灭了——夜幕落下，梦魇从墙缝里挤了出来。")

    def _nightmare_rooms(self, engine: Any, count: int, room_key: str) -> list[str]:
        """p140：优先带事件图标且离最近英雄 ≥4 格的房间，其次尽可能远。"""
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        candidates = []
        for key, room in sorted(engine.state.board.items()):
            if room.symbol != "event" or self.FURNACE == room.template_id:
                continue
            distance = min(
                (engine._path_length(key, hero.room_key) for hero in heroes),
                default=99,
            )
            candidates.append((distance, key))
        far = [key for distance, key in candidates if distance >= 4]
        pool = far or [key for _, key in sorted(candidates, reverse=True)]
        if not pool:
            pool = [room_key]
        # 尽量均匀分布：轮转取用
        return [pool[i % len(pool)] for i in range(count)]

    # ------------------------------------------------------- 暮色判定
    def _nightmares(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if m.template_id == self.NIGHTMARE]

    def _torch_rooms(self, engine: Any) -> set:
        """持火把者所在房间（火把抵消该房间的暮色）。"""
        torches = engine._haunt_flags().get("torches", {})
        return {
            p.room_key
            for p in engine.state.players
            if not p.dead and torches.get(str(p.id))
        }

    def _carries_torch(self, engine: Any, player: Any) -> bool:
        return bool(engine._haunt_flags().get("torches", {}).get(str(player.id)))

    def in_twilight(self, engine: Any, room_key: str) -> bool:
        """p69：该房间此刻是否处于暮色中。

        优先级：叛徒所在房间**永远**是暮色（p69/p140 明文，优先于一切豁免），
        其次豁免熔炉房/花园/墓地/天井/阳台/塔楼，再看已驱散楼层与火把。
        """
        room = engine.state.board.get(room_key)
        if room is None:
            return False
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and traitor.room_key == room_key:
            return True  # 叛徒所在房间永远是暮色（即使已死）
        if room.template_id in self.TWILIGHT_FREE:
            return False
        if room.floor in set(engine._haunt_flags().get("banished_floors", [])):
            return False
        if room_key in self._torch_rooms(engine):
            return False
        return True

    # ------------------------------------------------------- 战斗规则
    def attack_attr_override(
        self, engine: Any, attacker: Any, target: Any, default_attr: str
    ) -> str | None:
        """p69/p140：暮色中 explorers and monsters 不能做力量/速度攻击，改用知识。"""
        if default_attr not in ("might", "speed"):
            return None
        if self._carries_torch(engine, attacker):
            return None
        room_key = getattr(attacker, "room_key", None)
        if room_key and self.in_twilight(engine, room_key):
            return "knowledge"
        return None

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p140：正在缠梦的噩梦不能被攻击。"""
        haunting = engine._haunt_flags().get("haunting", {})
        if getattr(target, "template_id", "") == self.NIGHTMARE and target.id in haunting:
            return False
        return super().attack_allowed(engine, attacker, target)

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p69：噩梦受 2 点以上伤害即被摧毁（否则只是击晕）。"""
        if getattr(monster, "template_id", "") != self.NIGHTMARE:
            return False
        if amount >= 2:
            engine.state.monsters = [m for m in engine.state.monsters if m.id != monster.id]
            engine._haunt_flags().get("haunting", {}).pop(monster.id, None)
            engine._log(f"{monster.name} 在尖啸中碎成了黑烟——它被彻底摧毁了。")
            return True
        engine._log(f"{monster.name} 只是被打散了一瞬。")
        engine._stun_monster(monster, 1)
        return True  # 全权接管：不足 2 点只击晕，引擎默认路径已跳过

    def on_player_died(self, engine: Any, player: Any) -> None:
        """p140：被缠梦的英雄倒下 → 梦魇必须松开他回到场上。

        缠梦的标记是「把梦魇 token 放在该英雄的角色卡上」——卡随人离场，
        梦魇不能继续贴着一张不存在的卡。不释放的后果是两条胜利线同时被掐断：
        `attack_allowed` 因 `id in haunting` 永久拒绝攻击这只梦魇（原文
        「Nightmares currently haunting a hero's dreams may not be attacked」），
        而 `on_monster_turn_start` 又让它整回合跳过；英雄这边「数位英雄同房 +
        持火把」的驱散条件在只剩一人时本就不成立（p69 明文）。
        实测 seed63/5p、seed3/5p：全场只剩的梦魇都缠着已死英雄，300 回合无人能胜。
        """
        flags = engine._haunt_flags()
        haunting = dict(flags.get("haunting", {}))
        released = [mid for mid, hid in haunting.items() if hid == player.id]
        if not released:
            return
        for mid in released:
            haunting.pop(mid, None)
            monster = next((m for m in engine.state.monsters if m.id == mid), None)
            if monster is not None and player.room_key:
                # 与「英雄挣脱后梦魇现身在英雄房间」同一口径（p140）。
                monster.room_key = player.room_key
        flags["haunting"] = haunting
        engine._log("梦魇从倒下的英雄身上松开，重新在房间里凝出形体。")

    # ------------------------------------------------------- 噩梦回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if getattr(monster, "template_id", "") != self.NIGHTMARE:
            return False
        # p140：正在缠梦的噩梦可以选择继续缠（bot 选择继续）
        if monster.id in engine._haunt_flags().get("haunting", {}):
            return True
        return False

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p140：噩梦以知识攻击；造成 ≥2 精神伤害时改为缠梦。"""
        if getattr(monster, "template_id", "") != self.NIGHTMARE:
            return False
        flags = engine._haunt_flags()
        if monster.id in flags.get("haunting", {}):
            return True
        target = engine._find_monster_target(monster)
        if target is None or target.room_key != monster.room_key:
            return True
        roll = engine._roll_monster_attack(monster, "knowledge")
        defense = engine._roll_attack(target, "knowledge")
        engine._log(f"噩梦扑进 {engine._player_label(target)} 的脑海：{roll} 对 {defense}。")
        if roll - defense >= 2:
            haunting = dict(flags.get("haunting", {}))
            haunting[monster.id] = target.id
            flags["haunting"] = haunting
            engine._log(f"{engine._player_label(target)} 被拖进了梦魇——噩梦缠住了他。")
        elif roll > defense:
            engine._deal_damage(target, "mental", roll - defense, source="噩梦")
        elif roll < defense:
            engine._stun_monster(monster, 1)
        return True

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """p140：被缠梦的英雄回合开始做理智 5+ 挣脱。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        flags = engine._haunt_flags()
        haunting = dict(flags.get("haunting", {}))
        mine = [mid for mid, hid in haunting.items() if hid == player.id]
        if not mine:
            return
        if engine._resolve_check(player, "sanity", 5, "挣脱梦魇"):
            for mid in mine:
                monster = next(
                    (m for m in engine.state.monsters if m.id == mid), None
                )
                if monster is not None:
                    monster.room_key = player.room_key  # 现身于英雄房间
                    monster.stunned_turns = 1
                haunting.pop(mid, None)
            flags["haunting"] = haunting
            engine._log(f"{engine._player_label(player)} 挣脱了梦魇——噩梦现身在房间里。")
            return
        engine._deal_damage(player, "mental", engine.roll_damage_dice(1, "梦魇伤害"), source="梦魇")
        engine._log(f"{engine._player_label(player)} 没能甩开梦魇，精神被啃噬了一口。")

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            # 造火把：只能在熔炉房（p69）
            if aid == "create_torch":
                if self._carries_torch(engine, player):
                    continue
                room = engine.state.board.get(player.room_key)
                if room is None or room.template_id != self.FURNACE:
                    continue
            # 驱散暮色：同房 ≥2 名活英雄 + 至少一人持火把 + 该房本该有暮色
            if aid == "banish_twilight" and not self._banish_allowed(engine, player):
                continue
            result.append(action)
        return result

    def _banish_allowed(self, engine: Any, player: Any) -> bool:
        room = engine.state.board.get(player.room_key)
        if room is None or room.floor in set(engine._haunt_flags().get("banished_floors", [])):
            return False
        here = [
            p
            for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == player.room_key
        ]
        if len(here) < 2:
            return False
        if not any(self._carries_torch(engine, p) for p in here):
            return False
        # 该房间"本该"有暮色（无火把时）——用房间模板与楼层判定
        return room.template_id not in self.TWILIGHT_FREE

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "create_torch":
            return self._create_torch(engine, player)
        if action_id == "banish_twilight":
            return self._banish_twilight(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _create_torch(self, engine: Any, player: Any) -> bool:
        """p69：在熔炉房造一支火把（代替攻击）。"""
        room = engine.state.board.get(player.room_key)
        if room is None or room.template_id != self.FURNACE:
            return False
        flags = engine._haunt_flags()
        torches = dict(flags.get("torches", {}))
        torches[str(player.id)] = True
        flags["torches"] = torches
        player.attack_used = True  # p69：代替攻击
        # 会合点按点火这一刻的站位钉死，之后不再跟着人漂——否则两人互追。
        flags["rally_key"] = self._compute_rally_room(engine)
        engine._log(f"{engine._player_label(player)} 在熔炉里点燃了一支火把。")
        return True

    def _banish_twilight(self, engine: Any, player: Any) -> bool:
        """p69：同房英雄各做一次知识 4+ 或理智 4+，需两类各至少一次成功。"""
        if not self._banish_allowed(engine, player):
            return False
        room = engine.state.board[player.room_key]
        here = [
            p
            for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == player.room_key
        ]
        knowledge_ok = False
        sanity_ok = False
        for hero in here:
            # p69：每位英雄各做一次知识 4+ 或理智 4+，团队需要"两类各至少一次成功"。
            # 缺哪类就补哪类——但只派给掷得出 4+ 的人。知识已成、这人理智 1
            # 时硬派理智，等于把一次必败检定浪费掉。
            stat = self._banish_stat_for(engine, hero, knowledge_ok, sanity_ok)
            if engine._resolve_check(hero, stat, self.BANISH_TARGET, "驱散暮色"):
                if stat == "knowledge":
                    knowledge_ok = True
                else:
                    sanity_ok = True
            # p69：做检定的英雄本回合不能移动或攻击
            hero.movement_stopped = True
            hero.attack_used = True
        if not (knowledge_ok and sanity_ok):
            engine._log("两种心智没能同时奏效——暮色依旧笼罩着这一层。")
            return False
        flags = engine._haunt_flags()
        floors = sorted(set(flags.get("banished_floors", [])) | {room.floor})
        flags["banished_floors"] = floors
        # 这一层清完，会合点改到还没驱散的最近暮色房——两人还在一起，一起换层。
        flags["rally_key"] = self._nearest_twilight_to(engine, player.room_key)
        engine._log(f"火光与意志同时亮起——{room.floor} 层的暮色被驱散了！")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p69：消灭所有噩梦 → 英雄胜
        if not self._nightmares(engine):
            engine._set_winner("heroes", "最后一只噩梦也散了——天亮了。")
            return True
        # p69：三层暮色全部驱散 → 英雄胜
        if set(self.FLOORS).issubset(set(flags.get("banished_floors", []))):
            engine._set_winner("heroes", "整栋房子的暮色都被驱散了——长夜结束。")
            return True
        # p140：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "梦魇吞下了最后一个人。")
            return True
        # 吸收兜底：叛徒出局时噩梦照常行动（7/8 号怪物自主口径）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def _alive_heroes(self, engine: Any) -> list[Any]:
        return [p for p in engine.state.players if p.role == "hero" and not p.dead]

    def _team_has_torch(self, engine: Any) -> bool:
        return any(self._carries_torch(engine, p) for p in self._alive_heroes(engine))

    def _twilight_rooms_on_floor(self, engine: Any, floor: int) -> list[str]:
        return [
            key
            for key, room in engine.state.board.items()
            if room.floor == floor and room.template_id not in self.TWILIGHT_FREE
        ]

    def _is_stop_risk_room(self, engine: Any, room_key: str) -> bool:
        room = engine.state.board.get(room_key)
        if room is None:
            return True
        return bool(engine.room_stop_risk(room))

    def _can_make_check(self, engine: Any, player: Any, stat: str, target: int) -> bool:
        value = max(0, int(player.stats.get(stat, 0) or 0))
        dice = max(1, min(8, value))
        return dice * 2 >= int(target)

    def _banish_stat_for(
        self, engine: Any, hero: Any, knowledge_ok: bool, sanity_ok: bool
    ) -> str:
        can_knowledge = self._can_make_check(engine, hero, "knowledge", self.BANISH_TARGET)
        can_sanity = self._can_make_check(engine, hero, "sanity", self.BANISH_TARGET)
        if knowledge_ok and not sanity_ok and can_sanity:
            return "sanity"
        if sanity_ok and not knowledge_ok and can_knowledge:
            return "knowledge"
        if can_knowledge and (
            not can_sanity
            or int(hero.stats.get("knowledge", 0) or 0)
            >= int(hero.stats.get("sanity", 0) or 0)
        ):
            return "knowledge"
        if can_sanity:
            return "sanity"
        return (
            "knowledge"
            if int(hero.stats.get("knowledge", 0) or 0)
            >= int(hero.stats.get("sanity", 0) or 0)
            else "sanity"
        )

    def _twilight_candidates(self, engine: Any) -> list[str]:
        banished = set(engine._haunt_flags().get("banished_floors", []))
        twilight = [
            key
            for key, room in engine.state.board.items()
            if room.floor not in banished and room.template_id not in self.TWILIGHT_FREE
        ]
        safe = [key for key in twilight if not self._is_stop_risk_room(engine, key)]
        return safe or twilight

    def _nearest_twilight_to(self, engine: Any, from_key: str) -> str | None:
        """还没驱散的暮色房里，离 from_key 最近的一间；效果房只作后备。"""
        pool = self._twilight_candidates(engine)
        if not pool or not from_key:
            return None
        best_key = None
        best_score = None
        for key in pool:
            distance = engine._path_length(from_key, key, avoid_transit=True)
            if distance >= 9999:
                continue
            score = (distance, key)
            if best_score is None or score < best_score:
                best_score = score
                best_key = key
        return best_key

    def _compute_rally_room(self, engine: Any) -> str | None:
        """按点火时的站位，挑火把持有者与最近队友的中途暮色房并钉死。

        只跟火把走会把人拽进保险库；只跟队友走，火把在地下室时两人永远凑不齐。
        中途暮色房是真人会约的地方。效果房不当落脚点。
        """
        heroes = self._alive_heroes(engine)
        holders = [hero for hero in heroes if self._carries_torch(engine, hero)]
        if not holders:
            return None
        holder = min(holders, key=lambda hero: hero.id)
        others = [hero for hero in heroes if hero.id != holder.id]
        if not others:
            return self._nearest_twilight_to(engine, holder.room_key)
        other = min(
            others,
            key=lambda hero: (
                engine._path_length(holder.room_key, hero.room_key, avoid_transit=True),
                hero.id,
            ),
        )
        pool = self._twilight_candidates(engine)
        best_key = None
        best_score = None
        for key in pool:
            dist_holder = engine._path_length(holder.room_key, key, avoid_transit=True)
            dist_other = engine._path_length(other.room_key, key, avoid_transit=True)
            if dist_holder >= 9999 or dist_other >= 9999:
                continue
            floor = engine.state.board[key].floor
            score = (
                -(dist_holder + dist_other),
                -max(dist_holder, dist_other),
                0 if floor == 0 else -abs(floor),
                key,
            )
            if best_score is None or score > best_score:
                best_score = score
                best_key = key
        return best_key or self._nearest_twilight_to(engine, holder.room_key)

    def _rally_still_valid(self, engine: Any, room_key: str | None) -> bool:
        if not room_key:
            return False
        room = engine.state.board.get(room_key)
        if room is None or room.template_id in self.TWILIGHT_FREE:
            return False
        if room.floor in set(engine._haunt_flags().get("banished_floors", [])):
            return False
        if self._is_stop_risk_room(engine, room_key) and any(
            not self._is_stop_risk_room(engine, key)
            for key in self._twilight_candidates(engine)
        ):
            return False
        return True

    def _rally_room(self, engine: Any) -> str | None:
        """会合点优先用点火/驱散时钉死的房间，避免两人互追。"""
        flags = engine._haunt_flags()
        stored = flags.get("rally_key")
        if self._rally_still_valid(engine, stored):
            return stored
        return self._compute_rally_room(engine)

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        flags = engine._haunt_flags()
        heroes = self._alive_heroes(engine)
        # 驱散要两个人。只剩一人就改杀噩梦（另一条胜线）。
        if len(heroes) < 2:
            if not self._carries_torch(engine, player):
                furnace = flags.get("furnace_key")
                return [f"__room__{furnace}"] if furnace else []
            return [
                f"__room__{monster.room_key}"
                for monster in engine.state.monsters
                if monster.template_id == self.NIGHTMARE and monster.room_key
            ]
        # 全队还没火把：先去熔炉房点一支。已经有人点着了就别再排队熔炉房——
        # create_torch 的 rooms 会把熔炉房塞进目标，人会点完火把还往回聚，
        # 熔炉房又不在暮色里，驱散永远凑不齐三层。
        if not self._team_has_torch(engine):
            furnace = flags.get("furnace_key")
            return [f"__room__{furnace}"] if furnace else []
        rally = self._rally_room(engine)
        if rally:
            return [f"__room__{rally}"]
        # 场上还没有可驱散的暮色房（那一层还没铺出来）→ 改杀噩梦
        return [
            f"__room__{monster.room_key}"
            for monster in engine.state.monsters
            if monster.template_id == self.NIGHTMARE and monster.room_key
        ]

    def bot_goal_suppressed(self, engine: Any, player: Any) -> bool:
        """叛徒没有剧本房间目标。不压住的话 key_rooms 保底会把熔炉房当成目的地。"""
        return getattr(player, "role", None) == "traitor"

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        if action_id == "create_torch":
            if self._carries_torch(engine, player):
                return True
            # 队里已有火把、还够两个人驱散：别再把全员拽去熔炉房。
            if len(self._alive_heroes(engine)) >= 2 and self._team_has_torch(engine):
                return True
            return False
        if action_id == "banish_twilight":
            return not self._banish_allowed(engine, player)
        return False

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        if getattr(player, "role", None) != "hero":
            return False
        room = engine.state.board.get(player.room_key)
        if room is None:
            return False
        # 点完火把立刻离开熔炉房（那里驱散不了）。
        if room.template_id == self.FURNACE and self._carries_torch(engine, player):
            return True
        # 这一层已经驱散完，换层。
        if room.floor in set(engine._haunt_flags().get("banished_floors", [])):
            return True
        return False

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """火把到了会合房就停，等人来齐再驱散——别在同层暮色房间之间踱步。"""
        if getattr(player, "role", None) != "hero" or getattr(player, "dead", False):
            return False
        if len(self._alive_heroes(engine)) < 2 or not self._team_has_torch(engine):
            return False
        room = engine.state.board.get(player.room_key)
        if room is None or room.template_id in self.TWILIGHT_FREE:
            return False
        if self._is_stop_risk_room(engine, player.room_key):
            return False
        return player.room_key == self._rally_room(engine)

    def bot_attack_blocked(self, engine: Any, player: Any, target: Any) -> bool:
        """没火把就别在暮色里拿拳头捶噩梦——知识骰对 Might 2 的怪不划算，先去点火把。"""
        if getattr(player, "role", None) != "hero":
            return False
        if getattr(target, "template_id", "") != self.NIGHTMARE:
            return False
        return not self._carries_torch(engine, player)

    def bot_hazard_rooms(self, engine: Any, player: Any) -> set[str]:
        """没火把时别在噩梦房间过夜——去熔炉房的路上绕开，别自己送进嘴里。"""
        if getattr(player, "role", None) != "hero" or self._carries_torch(engine, player):
            return set()
        return {
            monster.room_key
            for monster in engine.state.monsters
            if monster.template_id == self.NIGHTMARE and monster.room_key
        }

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        banished = flags.get("banished_floors", [])
        lines = [f"已驱散楼层：{len(banished)}/3（{sorted(banished)}）。"]
        torches = flags.get("torches", {})
        if torches:
            lines.append(f"火把：{len(torches)} 支。")
        haunting = flags.get("haunting", {})
        if haunting:
            lines.append(f"被梦魇缠住：{len(haunting)} 人。")
        lines.append(f"噩梦：{len(self._nightmares(engine))} 只。")
        return lines
