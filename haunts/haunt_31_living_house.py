"""LivingHouseMode（剧本 31）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    OPPOSITE_DOOR,
    _monster_id,
)


class LivingHouseMode(GenericModeHandler):
    """剧本 31 器官房（It's Alive!）。

    权威原文：英雄手册 p42 / 叛徒手册 p113。

    这座房子本身是一个活物：六种器官系统（胃/肺/牙/腺体/心脏/大脑）+
    抗体。全程不改 engine.py / ui.py / models.py / net/，仅 content.py 新增
    antibody/heart/brain 三个怪物模板（数据，非引擎逻辑）；所有机制映射到
    GenericModeHandler 既有钩子。

    规则实现（对照原文）：
        · 六器官房：英雄“进入房间”(on_enter_room) 或“开始回合”(on_turn_start)
          时按房间 template_id 查表结算，两者时机不同不会双触发。
            - 胃（dining_room/kitchen/larder/wine_cellar）：Sanity 掷骰，5+ 无事；
              失败受 1 精神伤害；掷出 0/1 改受 2 精神伤害并停止移动。
            - 肺（conservatory + 有连通门的相邻房）：Might 4+；相邻房失败→移入温室
              再掷一次（通过则存活于温室）；温室内失败→该英雄被杀死并掉落所有物品。
            - 牙（balcony/entrance_hall）：Speed 掷骰，4+ 无事；1-3 受 1 物理；0 受 2 物理。
            - 腺体（research_laboratory/operating_laboratory）：掷两骰（和 0-4）：
              4→全属性+1；3→-2 速度；2→-2 力量；1→-2 理智；0→-2 知识。
        · 心脏（organ_room，怪物，防御 Might 7）/大脑（attic，怪物，防御 Might 6）：
          防御时不造成伤害（monster_counterattack_disabled）；永不移动/攻击
          （on_monster_turn_start 返回 True）；仅持 omen_spear 者可攻击（attack_allowed）；
          攻击大脑前须先 Sanity 4+，否则回合结束且不攻击；被长矛击败即“杀死房子”（英雄胜）。
        · 抗体（Speed3/Might5/Sanity3，数量=英雄数）：可穿墙移动（on_monster_move）；
          心脏/大脑被攻击且失败时，立即从屋内别处取一只抗体回流到该房（on_attack_resolved）。
        · 胜负：长矛击败心脏或大脑→英雄胜；杀光所有英雄，或叛徒偷矛后在
          chasm/furnace_room/underground_lake 花一整回合扔掉销毁→叛徒胜。叛徒存活。

    解释性决策（原文含糊处）：
        ① 长矛来源：p42/p113 未说明英雄如何获得长矛，只说叛徒“从持有它的英雄处偷走”。
           → setup 时把 omen_spear 授予 turn_order 中第一名英雄（确定性）。
        ② 腺体“全属性+1”：用 engine._increase_stat(player, stat, 1)（含 overflow 处理，
           是 _apply_stat_loss 的对称方法），逐一对 speed/might/sanity/knowledge +1。
        ③ 抗体穿墙移动语义：原文只说“can move through walls”未给距离规则。→ 朝最近英雄
           移动，忽略连通门（同楼层网格相邻即视为可穿墙抵达，跨楼层仍借门/楼梯连通），
           按 board 房间计数距离取掷骰步数内最接近目标的房间（复用木乃伊 on_monster_move
           范式）；对不在场/未发现房间跳过避免 KeyError。
        ④ 器官令牌：胃/肺/牙/腺体不生成实体蓝色器官令牌，改由房间 template_id 运行时
           查表判定——因此 p113“房间尚未出现时待其被发现再放令牌”自动满足（模板判定
           天然只在房间被发现/进入后生效）；rule_data 的 tokens 字段仅作 UI/配件提示保留。

    已知简化：
        · 攻击心脏/大脑“平手”时引擎在 on_attack_resolved 之前提前返回，故平手不触发
          抗体回流（仅“攻击落败”触发，与原文“attack fails”的主路径一致）。
        · 器官房的分档掷骰（胃/牙用 _roll_attack 取原始骰值、腺体用 roll_dice(2)）不走
          _resolve_check 的重掷/保存骰/护身符交互（与女妖哀鸣 _wail 先例一致）；肺与大脑
          的纯阈值检定走 _resolve_check，保留英雄的重掷能力。
        · 抗体穿墙（on_monster_move）仅在引擎调用该钩子时生效，而引擎只在“门/楼梯图
          存在到目标的路径（len(path)>1）”时才调用它；故抗体与最近英雄完全无门连通时
          本回合不相位（与木乃伊秘密通道先例同款的引擎级门控）。同楼层网格相邻即可
          穿墙抵达，但跨楼层仍须借门/楼梯触发钩子。
        · 长矛击杀语义：器官须“被长矛击败”（monster_killed_on_defeat 的 weapon_id==
          omen_spear）才杀死房子；仅“持有长矛”却空手或用异武器攻击只会击晕心脏/大脑、
          不置 house_killed（bot 选最高分武器必选长矛，无此问题；人类玩家需注意）。
    """

    mode = "living_house"

    HEART = "heart"
    BRAIN = "brain"
    ANTIBODY = "antibody"
    SPEAR = "omen_spear"
    STOMACH_ROOMS = ("dining_room", "kitchen", "larder", "wine_cellar")
    TEETH_ROOMS = ("balcony", "entrance_hall")
    GLANDS_ROOMS = ("research_laboratory", "operating_laboratory")
    CONSERVATORY = "conservatory"
    ANTIBODY_ROOMS = (
        "research_laboratory", "operating_laboratory", "entrance_hall",
        "furnace_room", "underground_lake", "library",
    )
    GRID_DELTAS = ((-1, 0), (0, -1), (0, 1), (1, 0))

    # ============================================================= setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        """p42/p113：放心脏（管风琴室）/大脑（阁楼）怪物、授予长矛、布抗体，
        并对当前处于胃房间的英雄立即各掷一次胃检定（按 turn_order 顺序）。"""
        flags = engine._haunt_flags()
        flags.setdefault("house_killed", False)
        flags.setdefault("spear_destroyed", False)
        # 心脏 / 大脑：房间不在场则拉进场
        organ_key = engine._ensure_room_in_play("organ_room", room_key)
        attic_key = engine._ensure_room_in_play("attic", room_key)
        if organ_key:
            engine._spawn_single_haunt_monster(self._spec(engine, self.HEART, "心脏"), organ_key)
        if attic_key:
            engine._spawn_single_haunt_monster(self._spec(engine, self.BRAIN, "大脑"), attic_key)
        # 长矛授予第一名英雄（解释性决策①）
        first_hero = self._first_hero(engine)
        if first_hero is not None:
            engine._grant_card_to_player(first_hero, self.SPEAR)
        # 抗体：数量=英雄数，均匀放入 6 指定房中在场者
        self._spawn_antibodies(engine)
        # setup 时当前在胃房间的英雄立即掷一次胃检定
        for player in self._heroes_in_turn_order(engine):
            room = engine.current_room(player)
            if room is not None and getattr(room, "template_id", "") in self.STOMACH_ROOMS:
                self._apply_stomach(engine, player)

    # ============================================================= 器官房查表
    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        self._apply_organ_effect(engine, player, room)

    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.dead:
            return
        self._apply_organ_effect(engine, player, engine.current_room(player))

    def _apply_organ_effect(self, engine: Any, player: Any, room: Any) -> None:
        """按房间 template_id 分派胃/肺/牙/腺体效果（仅影响英雄；Python 3.9 无 match，用 if 链）。"""
        if room is None or player.role != "hero" or player.dead:
            return
        template_id = getattr(room, "template_id", "")
        if not template_id:
            return
        if template_id in self.STOMACH_ROOMS:
            self._apply_stomach(engine, player)
            return
        if template_id in self.TEETH_ROOMS:
            self._apply_teeth(engine, player)
            return
        if template_id in self.GLANDS_ROOMS:
            self._apply_glands(engine, player)
            return
        if template_id == self.CONSERVATORY:
            self._apply_lungs(engine, player, in_conservatory=True)
            return
        # 肺的“相邻房”：与温室有连通门的房间
        conserv_key = self._room_key_by_template(engine, self.CONSERVATORY)
        if conserv_key and self._door_adjacent(engine, getattr(room, "key", ""), conserv_key):
            self._apply_lungs(engine, player, in_conservatory=False)

    def _apply_stomach(self, engine: Any, player: Any) -> None:
        """胃（消化）：Sanity 掷骰 5+ 无事；失败 1 精神伤害；0/1 → 2 精神伤害 + 停止移动。"""
        roll = engine._roll_attack(player, "sanity")
        engine._log(f"胃：{player.name} 在消化房里掷出理智 {roll}。")
        if roll >= 5:
            engine._log(f"{player.name} 稳住了心神，没有被胃液侵蚀。")
            return
        if roll <= 1:
            engine._deal_damage(player, "mental", 2, source="胃消化")
            player.movement_stopped = True
            engine._log(f"{player.name} 被胃液剧烈侵蚀（2 点精神伤害），停下脚步。")
        else:
            engine._deal_damage(player, "mental", 1, source="胃消化")

    def _apply_teeth(self, engine: Any, player: Any) -> None:
        """牙：Speed 掷骰 4+ 无事；1-3 受 1 物理；0 受 2 物理。"""
        roll = engine._roll_attack(player, "speed")
        engine._log(f"牙：{player.name} 在布满利齿的房间里掷出速度 {roll}。")
        if roll >= 4:
            engine._log(f"{player.name} 躲过了咬合的巨牙。")
            return
        engine._deal_damage(player, "physical", 2 if roll == 0 else 1, source="巨牙")

    def _apply_glands(self, engine: Any, player: Any) -> None:
        """腺体：掷两骰（和 0-4）：4→全属性+1；3→-2速度；2→-2力量；1→-2理智；0→-2知识。"""
        roll = engine.roll_dice(2, "腺体")
        engine._log(f"腺体：{player.name} 掷出两枚骰，和为 {roll}。")
        if roll >= 4:
            for stat in ("speed", "might", "sanity", "knowledge"):
                engine._increase_stat(player, stat, 1)  # 解释性决策②
            engine._log(f"{player.name} 被腺体分泌物强化（全属性 +1）。")
        elif roll == 3:
            engine._apply_stat_loss(player, "speed", 2)
        elif roll == 2:
            engine._apply_stat_loss(player, "might", 2)
        elif roll == 1:
            engine._apply_stat_loss(player, "sanity", 2)
        else:
            engine._apply_stat_loss(player, "knowledge", 2)
        engine._check_player_death(player)  # -2 降到骷髅（0）即死

    def _apply_lungs(self, engine: Any, player: Any, in_conservatory: bool) -> None:
        """肺（呼吸）：Might 4+；相邻房失败→移入温室再掷一次；温室内失败→被杀死并掉落物品。"""
        if engine._resolve_check(player, "might", 4, "抵抗房屋的肺"):
            engine._log(f"{player.name} 撑住了肺的挤压。")
            return
        if not in_conservatory:
            conserv_key = self._room_key_by_template(engine, self.CONSERVATORY)
            if conserv_key:
                player.room_key = conserv_key
                engine._log(f"肺把 {player.name} 吸进了温室！")
                if engine._resolve_check(player, "might", 4, "在温室中抵抗肺"):
                    engine._log(f"{player.name} 在温室里稳住了，但已被困在此处。")
                    return
        engine._log(f"{player.name} 在温室里被房屋的肺活活憋死！")
        player.dead = True
        engine._drop_inventory_on_death(player)
        engine.check_victory()

    # ============================================================= 心脏 / 大脑
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """仅持长矛者可攻击心脏/大脑；攻击大脑前须先 Sanity 4+，否则回合结束且不攻击。

        本方法会被 bot 的**预判**路径调用（`attack_would_be_allowed`，引擎在
        该路径把 `engine._attack_query` 置 True）。预判必须无副作用——不能掷骰、
        不能改 `attack_used/movement_stopped/steps_remaining`、也不要刷日志，
        否则机器人在走位评分阶段就被自己的查询冻结、日志还会被"只有长矛能伤到
        心脏"刷屏（M10-49 实测一局 80-120 行）。预判阶段对持矛者一律返回 True
        （"理论上打得着"），理智检定留到真打那一次。
        """
        mid = _monster_id(target)
        if mid not in (self.HEART, self.BRAIN):
            return True
        query = bool(getattr(engine, "_attack_query", False))
        if self.SPEAR not in (getattr(attacker, "items", None) or []):
            if not query:
                engine._log(f"只有长矛能伤到{'心脏' if mid == self.HEART else '大脑'}。")
            return False
        if mid == self.BRAIN and not query and not engine._resolve_check(
            attacker, "sanity", 4, "直视房屋的大脑"
        ):
            # p113：“his or her turn ends without attacking”。引擎移动闸门只看
            # dead/movement_stopped（不看 attack_used），故必须同时停移动、清空剩余
            # 移动力，否则英雄攻脑失败后仍能带完整步数白嫖离开阁楼。
            attacker.attack_used = True  # 回合结束且不攻击
            attacker.movement_stopped = True
            attacker.steps_remaining = 0
            engine._log(f"{attacker.name} 无法直视大脑，回合就此结束。")
            return False
        return True

    def monster_counterattack_disabled(self, engine: Any, monster: Any) -> bool:
        """心脏/大脑防御时不造成伤害。"""
        return _monster_id(monster) in (self.HEART, self.BRAIN)

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """被长矛击败即杀死房子（英雄胜）；非长矛（理论上被 attack_allowed 拦住）仅击晕。"""
        mid = _monster_id(monster)
        if mid not in (self.HEART, self.BRAIN):
            return False
        if weapon_id == self.SPEAR:
            engine._haunt_flags()["house_killed"] = True
            engine._set_haunt_track_value("house_slain", 1)
            engine._log(f"长矛刺穿了房屋的{'心脏' if mid == self.HEART else '大脑'}——这座活房子死了！")
            return True
        return False

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        """心脏/大脑被攻击且失败 → 从屋内别处取一只抗体回流到该房。"""
        mid = _monster_id(target)
        if mid not in (self.HEART, self.BRAIN) or attacker_won:
            return
        self._reflow_antibody(engine, getattr(target, "room_key", ""))

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """心脏/大脑永不移动/攻击（return True = 本回合不再行动）。"""
        return _monster_id(monster) in (self.HEART, self.BRAIN)

    # ============================================================= 抗体穿墙移动
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """抗体可穿墙：朝最近英雄移动，忽略连通门（解释性决策③）。"""
        if _monster_id(monster) != self.ANTIBODY:
            return False
        target = engine._find_monster_target(monster)
        if target is None or monster.room_key == target.room_key:
            return True  # 无目标或已在目标房：已处理（引擎随后会照常攻击同房目标）
        dest = self._wall_step_destination(engine, monster.room_key, target.room_key, max(0, int(rolled)))
        if dest and dest != monster.room_key:
            monster.room_key = dest
            room = engine.state.board.get(dest)
            engine._log(f"{monster.name} 穿过墙壁移动到{room.name if room else dest}。")
        return True

    # ============================================================= 叛徒销毁长矛
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        """throw_spear：叛徒在深渊/熔炉房/地下湖花一整回合把偷来的长矛销毁 → 叛徒胜。"""
        if action_id == "throw_spear":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and not engine._haunt_flags().get("spear_destroyed"):
                engine._haunt_flags()["spear_destroyed"] = True
                engine._discard_card_from_player(player, self.SPEAR, return_to_room=False)
                engine._log("叛徒把长矛投入深渊——房屋的克星就此消失！")
            return ok
        return super().perform_action(engine, player, action_id, data)

    # ============================================================= 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        if flags.get("house_killed"):
            engine._set_winner("heroes", "长矛杀死了活房子的心脏/大脑——这座房子终于死了。")
            return True
        if flags.get("spear_destroyed"):
            engine._set_winner("traitor", "长矛被销毁，再没有什么能杀死这座活房子。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "所有英雄都被活房子消化了。")
            return True
        return True  # 叛徒存活；吸收引擎“叛徒死亡→英雄胜”兜底（杀叛徒≠杀死房子）

    # ============================================================= 进度摘要
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        """公开信息：心脏/大脑存活、抗体数量与分布、长矛持有者/是否已销毁。"""
        flags = engine._haunt_flags()
        lines: list[str] = []
        heart = engine._monster_by_template(self.HEART)
        brain = engine._monster_by_template(self.BRAIN)
        lines.append("心脏：已被杀死" if heart is None else "心脏：存活（管风琴室，防御力量 7）")
        lines.append("大脑：已被杀死" if brain is None else "大脑：存活（阁楼，防御力量 6）")
        antibodies = [m for m in engine.state.monsters if _monster_id(m) == self.ANTIBODY]
        lines.append(f"抗体：{len(antibodies)} 只（可穿墙，护住心脏/大脑）")
        rooms: dict[str, int] = {}
        for m in antibodies:
            r = engine.state.board.get(m.room_key)
            name = r.name if r else m.room_key
            rooms[name] = rooms.get(name, 0) + 1
        if rooms:
            lines.append("抗体分布：" + "，".join(f"{k}×{v}" for k, v in sorted(rooms.items())))
        if flags.get("spear_destroyed"):
            lines.append("长矛：已被叛徒销毁。")
        else:
            holder = next(
                (p for p in engine.state.players if self.SPEAR in (getattr(p, "items", None) or []) and not p.dead),
                None,
            )
            lines.append(f"长矛：{holder.name + ' 持有' if holder else '不在任何人手上'}（只有它能杀死房子）。")
        return lines

    # ============================================================= 内部工具
    def _spec(self, engine: Any, template_id: str, name: str) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        spec = dict(specs.get(template_id) or {"template_id": template_id, "name": name})
        spec.setdefault("template_id", template_id)
        spec.setdefault("name", name)
        spec.setdefault("controller", "traitor")
        return spec

    def _spawn_antibodies(self, engine: Any) -> None:
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        count = len(heroes)
        if count <= 0:
            return
        in_play = sorted(
            {key for key in (self._room_key_by_template(engine, t) for t in self.ANTIBODY_ROOMS) if key}
        )
        if not in_play:
            return
        spec = self._spec(engine, self.ANTIBODY, "抗体")
        for i in range(count):
            engine._spawn_single_haunt_monster(spec, in_play[i % len(in_play)])  # round-robin 均匀分布

    def _reflow_antibody(self, engine: Any, dest_key: str) -> None:
        if not dest_key:
            return
        candidates = [
            m for m in engine.state.monsters
            if _monster_id(m) == self.ANTIBODY and m.room_key != dest_key
        ]
        if not candidates:
            return
        candidates.sort(key=lambda m: getattr(m, "id", ""))  # 确定性：取 id 最小且不在该房者
        moved = candidates[0]
        moved.room_key = dest_key
        room = engine.state.board.get(dest_key)
        engine._log(f"一只抗体穿过墙壁回流到{room.name if room else dest_key}，护住受伤的器官。")

    def _room_key_by_template(self, engine: Any, template_id: str) -> str | None:
        for key in sorted(engine.state.board):
            if engine.state.board[key].template_id == template_id:
                return key
        return None

    def _first_hero(self, engine: Any) -> Any | None:
        order = engine.state.turn_order
        if order:
            by_id = {p.id: p for p in engine.state.players}
            for pid in order:
                p = by_id.get(pid)
                if p is not None and p.role == "hero" and not p.dead:
                    return p
        for p in engine.state.players:
            if p.role == "hero" and not p.dead:
                return p
        return None

    def _heroes_in_turn_order(self, engine: Any) -> list[Any]:
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        order = engine.state.turn_order
        if order:
            by_id = {p.id: p for p in heroes}
            ordered = [by_id[pid] for pid in order if pid in by_id]
            seen = {p.id for p in ordered}
            ordered += [p for p in heroes if p.id not in seen]
            return ordered
        return heroes

    def _door_adjacent(self, engine: Any, key_a: str, key_b: str) -> bool:
        """两房间是否同楼层且有互相对接的门（复用 DragonSiege 写法）。"""
        a = engine.state.board.get(key_a)
        b = engine.state.board.get(key_b)
        if not a or not b or a.floor != b.floor or not key_a or not key_b:
            return False
        dx = b.x - a.x
        dy = b.y - a.y
        for direction, (ddx, ddy) in {
            "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
        }.items():
            if (dx, dy) == (ddx, ddy) and direction in a.doors and OPPOSITE_DOOR[direction] in b.doors:
                return True
        return False

    def _wall_graph(self, engine: Any) -> dict[str, list[str]]:
        """穿墙连通图：引擎门/楼梯图 ∪ 同楼层网格相邻（忽略门=穿墙）。输出排序列表保证确定性。"""
        collapse = getattr(engine, "COLLAPSE_KEY", "collapsed")
        graph: dict[str, dict[str, None]] = {
            key: dict.fromkeys(engine._build_graph().get(key, ())) for key in engine.state.board
        }
        for key in sorted(engine.state.board):
            room = engine.state.board[key]
            if room.data.get(collapse):
                continue
            for dx, dy in self.GRID_DELTAS:
                nk = engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
                if not nk or nk == key:
                    continue
                if engine.state.board[nk].data.get(collapse):
                    continue
                graph.setdefault(key, {})[nk] = None
                graph.setdefault(nk, {})[key] = None
        return {key: sorted(neighbors) for key, neighbors in graph.items()}

    def _bfs_dist(self, graph: dict[str, list[str]], start: str) -> dict[str, int]:
        dist = {start: 0}
        order = [start]
        i = 0
        while i < len(order):
            cur = order[i]
            i += 1
            for nb in graph.get(cur, ()):
                if nb not in dist:
                    dist[nb] = dist[cur] + 1
                    order.append(nb)
        return dist

    def _wall_step_destination(self, engine: Any, start_key: str, target_key: str, max_steps: int) -> str:
        """在 max_steps 步穿墙距离内，取最接近目标（穿墙距离最小）的房间；平手按 room_key。"""
        if max_steps <= 0:
            return start_key
        graph = self._wall_graph(engine)
        dist_target = self._bfs_dist(graph, target_key)
        dist_start = self._bfs_dist(graph, start_key)
        best_key = start_key
        best_rank = (dist_target.get(start_key, 9999), start_key)
        for key, d in dist_start.items():
            if d > max_steps:
                continue
            rank = (dist_target.get(key, 9999), key)
            if rank < best_rank:
                best_rank = rank
                best_key = key
        return best_key
