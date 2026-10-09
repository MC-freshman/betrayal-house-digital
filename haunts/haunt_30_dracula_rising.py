"""DraculaRisingMode（剧本 30）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class DraculaRisingMode(GenericModeHandler):
    """剧本 30 德古拉之墓（Tomb of Dracula）。

    权威原文：英雄手册 p41 / 叛徒手册 p112。

    已按原文实现：
        · 数值（p112 页脚，新增 dracula 与 bride 模板）：德古拉 速 5/力 8/
          智 6；新娘 4/4/4。
        · 开局（p112）：叛徒变吸血鬼（每项属性 +1）；德古拉放地窖或墓地，
          都不在场则放无人房距最近探索者 ≥4 格、再不行就最远（同 28 号
          地狱门口径）；女孩卡弃掉，新娘放在叛徒房间。
        · 时钟（p112）：叛徒回合开始把回合/伤害轨道推进到下一数字（从 1
          起）；随后立即由其他探险者之一掷「玩家数」枚骰，结果 < 当前
          回合数 → 日出（只发生一次）。叛徒出局后时钟由轮转首位存活玩家
          的回合开始代推（惯例）。
        · 日出后（p41）：每个叛徒回合开始，两只怪物吸血鬼每项属性各 -1
          （叛徒吸血鬼不弱化——原文只要求记录两只怪物的属性）；任一属性
          归零 → 昏迷不醒（on_monster_turn_start 跳过其行动）；英雄与昏迷
          吸血鬼同房间可"钉杀昏迷的吸血鬼"（每回合一次，代替攻击）；
          吸血鬼进入/身处 阳台/温室/花园/墓地/庭院/塔楼 立刻被阳光烧毁
          （其它朝外窗未建模，同 24 号口径）——叛徒吸血鬼同样会烧。
        · 圣物准入（p112）：吸血鬼怪物进教堂或持圣徽探险者的房间须理智
          6+，失败则停在门外（handler 接管移动逐房判定）；叛徒吸血鬼按
          硬阻挡简化（原文可掷骰硬闯，电子版避免移动选项列表期掷骰）。
        · 魅惑（p112）：吸血鬼可隔门从邻室对目标做理智攻击；赢则目标改受
          等额速度伤害、并可被拉进吸血鬼房间（bot 拉入）；输则吸血鬼不
          受伤。速度被魅惑打到见底 → 该角色变成吸血鬼：速度恢复初始值、
          每项属性 +1、引擎 role 改为 traitor（复用 bot 目标逻辑，同
          剧本 6 精神控制的电子化口径）。原文限定"异性目标"——角色数据
          无性别字段，对所有目标可用（同 20 号口径）。
        · 英雄杀法（p41）：长矛+力量攻击击败吸血鬼 = 钉杀（直接摧毁，
          monster_killed_on_defeat 按 weapon_id 判定）；其它成功攻击照常
          伤害/击晕；持圣徽者击败吸血鬼后按伤害点数把它沿门击退等距
          （on_monster_defeated 内结算，之后照常击晕）。
        · 胜负（p41/p112）：英雄胜 = 德古拉与新娘都被摧毁（钉杀/阳光烧毁
          均算）；叛徒胜 = 所有英雄死亡或变成吸血鬼。叛徒死亡后两只怪物
          照常行动（老坑 20 号吸收者）。

    已知简化：
        · 魅惑限定"异性目标"未建模（角色数据无性别字段，同 20 号）。
        · 叛徒吸血鬼的魅惑攻击未实现（原文 any Vampire 含叛徒；bot 叛徒
          按普通近战攻击处理）；其进教堂/圣徽房为硬阻挡而非 6+ 检定。
        · 怪物吸血鬼的移动由 handler 接管：逐房判圣物准入，但只在最终
          房间结算阳光燃烧（途经房间不判）。
        · "若叛徒获胜且吸血鬼杀了英雄，控制该吸血鬼的玩家也赢"——多胜方
          未建模（引擎单胜方）。
    """

    mode = "dracula_rising"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        rows = []
        if flags.get("sunrise"):
            rows.append("太阳已经升起——吸血鬼正在弱化")
        d = "已摧毁" if flags.get("dracula_destroyed") else "仍在"
        b = "已摧毁" if flags.get("bride_destroyed") else "仍在"
        rows.append(f"德古拉：{d}；新娘：{b}")
        return rows

    DRACULA = "dracula"
    BRIDE = "bride"
    VAMPIRE_MONSTERS = (DRACULA, BRIDE)
    SUNLIT_ROOMS = ("balcony", "conservatory", "garden", "graveyard", "patio", "tower")

    def __init__(self) -> None:
        self._defeat_ctx: tuple[str] | None = None

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("sunrise", False)
        flags.setdefault("vampire_ids", [])
        flags.setdefault("unconscious_ids", [])
        flags.setdefault("dracula_destroyed", False)
        flags.setdefault("bride_destroyed", False)
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        # p112：叛徒变吸血鬼，每项属性 +1
        if traitor is not None:
            self._boost(engine, traitor)
            self._mark_vampire(engine, traitor)
            engine._log(f"{traitor.name} 的獠牙长了出来——他也成了吸血鬼。")
        # p112：德古拉 → 地窖或墓地。两者都不在场时不能退而求其次去"任意远房"：
        # 巢穴是剧本机制的一部分（长矛钉杀、阳光烧毁都以"德古拉在巢穴"为前提，
        # 测试与黄金基准也按地窖/墓地断言）。用引擎能力把房间拉进场——与 2 号
        # 五芒星室、3 号温室同一做法；实在拉不进来（牌堆耗尽/放不下）才退回远房。
        drac_key = self._first_in_play(engine, ("crypt", "graveyard"))
        if not drac_key:
            drac_key = engine._ensure_room_in_play("crypt") or engine._ensure_room_in_play(
                "graveyard"
            )
        if not drac_key:
            drac_key = self._far_unoccupied(engine)
        specs = engine._haunt_rule_state().get("monster_specs", {})
        if drac_key:
            engine._spawn_single_haunt_monster(
                dict(specs.get(self.DRACULA) or {"template_id": self.DRACULA}), drac_key
            )
            engine._log("棺盖自己滑开了——地底传来德古拉苏醒前的第一声呼吸。")
        # p112：弃掉女孩卡，新娘放在叛徒房间
        self._discard_girl(engine)
        if traitor is not None:
            engine._spawn_single_haunt_monster(
                dict(specs.get(self.BRIDE) or {"template_id": self.BRIDE}), traitor.room_key
            )
            engine._log("女孩的身影在阴影里扭成了德古拉的新娘——她就站在叛徒身边。")

    def _boost(self, engine: Any, player: Any) -> None:
        """p112：每项属性 +1（按数值加，跳过轨道同值格）。"""
        for stat in ("might", "speed", "sanity", "knowledge"):
            track = engine._stat_track(player, stat)
            target_value = player.stats[stat] + 1
            if track is not None:
                idx = next((i for i, v in enumerate(track) if v >= target_value), len(track) - 1)
                player.stat_positions[stat] = idx
                player.stats[stat] = track[idx]
            else:
                player.stats[stat] = player.stats[stat] + 1

    def _first_in_play(self, engine: Any, template_ids: tuple[str, ...]) -> str:
        for template_id in template_ids:
            key = next(
                (k for k, room in engine.state.board.items() if room.template_id == template_id),
                "",
            )
            if key:
                return key
        return ""

    def _far_unoccupied(self, engine: Any) -> str:
        alive = [p for p in engine.state.players if not p.dead]
        candidates: list[tuple[int, str]] = []
        for key, room in engine.state.board.items():
            if engine.room_occupants(key) or engine._is_collapsed(key):
                continue
            dist = min((engine._path_length(key, p.room_key) for p in alive), default=99)
            candidates.append((dist, key))
        if not candidates:
            return ""
        far = max(dist for dist, _ in candidates)
        eligible = sorted(key for dist, key in candidates if dist >= 4)
        if not eligible:
            eligible = sorted(key for dist, key in candidates if dist == far)
        return eligible[0]

    def _discard_girl(self, engine: Any) -> None:
        for player in engine.state.players:
            if "omen_girl" in player.items:
                engine._discard_card_from_player(player, "omen_girl", return_to_room=False)
                engine._log("女孩卡在众人眼前化作一撮尘土（p112）。")
                return
        for key, items in engine.state.room_items.items():
            if "omen_girl" in items:
                items.remove("omen_girl")
                engine._log("躺在房间里的女孩卡化作一撮尘土（p112）。")
                return
        for deck in engine.state.card_decks.values():
            if "omen_girl" in deck:
                deck.remove("omen_girl")
                engine._log("牌堆里的女孩卡无声无息地消失了（p112）。")
                return
        for discard in engine.state.card_discards.values():
            if "omen_girl" in discard:
                discard.remove("omen_girl")
                engine._log("弃牌堆里的女孩卡无声无息地消失了（p112）。")
                return

    # ----------------------------------------------------------- 状态查询
    def _is_vampire_player(self, engine: Any, player: Any) -> bool:
        return str(getattr(player, "id", "")) in {
            str(i) for i in engine._haunt_flags().get("vampire_ids", [])
        }

    def _vampire_monsters(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) in self.VAMPIRE_MONSTERS]

    def _unconscious_ids(self, engine: Any) -> set[str]:
        return {str(i) for i in engine._haunt_flags().get("unconscious_ids", [])}

    def _destroy_vampire(self, engine: Any, monster: Any, killer: Any, reason: str) -> None:
        if _monster_id(monster) == self.DRACULA:
            engine._haunt_flags()["dracula_destroyed"] = True
        elif _monster_id(monster) == self.BRIDE:
            engine._haunt_flags()["bride_destroyed"] = True
        engine._log(reason)
        engine._kill_monster(monster, killer=killer)
        engine.check_victory()

    # ------------------------------------------------- 时钟与日出（p112）
    def on_turn_start(self, engine: Any, player: Any) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor" and not p.dead), None)
        if traitor is not None:
            if player.id != traitor.id:
                return
        else:
            # 叛徒出局：时钟改由轮转顺序里第一位存活玩家代推（惯例）
            order = engine.state.turn_order
            first_alive = next(
                (pid for pid in order if any(p.id == pid and not p.dead for p in engine.state.players)),
                None,
            )
            if player.id != first_alive:
                return
        self._advance_clock(engine)

    def _advance_clock(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        value = engine._advance_haunt_track("sun_track", 1)
        if not flags.get("sunrise"):
            # p41：轨道推进后立即由其他探险者之一掷「玩家数」枚骰
            roller = next(
                (p for p in engine.state.players if p.role == "hero" and not p.dead),
                None,
            )
            roll = engine.roll_dice(len(engine.state.players), "日出检定")
            if roll < value:
                flags["sunrise"] = True
                engine._log(f"日出检定 {roll} < 回合数 {value}——太阳升起来了！（p41）")
            else:
                engine._log(f"日出检定 {roll} ≥ 回合数 {value}，夜还深着。")
        else:
            # p41：两只怪物吸血鬼每项属性各 -1（叛徒吸血鬼不弱化）
            for monster in self._vampire_monsters(engine):
                if monster.id in self._unconscious_ids(engine):
                    continue
                for stat in ("speed", "might", "sanity"):
                    setattr(monster, stat, max(0, getattr(monster, stat) - 1))
                if any(getattr(monster, s) <= 0 for s in ("speed", "might", "sanity")):
                    engine._haunt_flags().setdefault("unconscious_ids", []).append(monster.id)
                    engine._log(f"{monster.name} 在阳光下不支倒地，昏迷不醒——快去钉杀它！")
        self._burn_vampires_in_sunlight(engine)
        engine.check_victory()

    def _burn_vampires_in_sunlight(self, engine: Any) -> None:
        """p41：日出后吸血鬼进入/身处向阳房间即被烧毁（含叛徒吸血鬼）。"""
        if not engine._haunt_flags().get("sunrise"):
            return
        for monster in list(self._vampire_monsters(engine)):
            room = engine.state.board.get(monster.room_key)
            if room is not None and room.template_id in self.SUNLIT_ROOMS:
                self._destroy_vampire(
                    engine, monster, None,
                    f"阳光灌进{room.name}——{monster.name} 尖啸着燃烧殆尽！",
                )
        for player in engine.state.players:
            if player.dead or not self._is_vampire_player(engine, player):
                continue
            room = engine.state.board.get(player.room_key)
            if room is not None and room.template_id in self.SUNLIT_ROOMS:
                engine._log(f"{player.name} 站进了阳光里——皮肤冒烟、燃成灰烬！")
                for stat in ("might", "speed", "sanity", "knowledge"):
                    player.stats[stat] = 0
                engine._check_player_death(player)

    def on_player_moved(self, engine: Any, player: Any) -> None:
        if self._is_vampire_player(engine, player):
            self._burn_vampires_in_sunlight(engine)

    # ------------------------------------------------- 圣物准入（p112）
    def _holy_blocked(self, engine: Any, monster: Any, room_key: str) -> bool:
        """吸血鬼怪物进入教堂/持圣徽者的房间须理智 6+；返回 True = 被逼退。"""
        room = engine.state.board.get(room_key)
        if room is None:
            return False
        has_symbol = any(
            p.role == "hero" and not p.dead and "omen_holy_symbol" in p.items
            and p.room_key == room_key
            for p in engine.state.players
        )
        if room.template_id != "chapel" and not has_symbol:
            return False
        roll = engine._roll_monster_attack(monster, "sanity")
        if roll >= 6:
            engine._log(f"{monster.name} 硬顶着圣物之力闯了进去（理智检定 {roll}）。")
            return False
        engine._log(f"{monster.name} 被圣物之力逼退（理智检定 {roll} < 6）。")
        return True

    def room_entry_blocked(self, engine: Any, player: Any, room: Any) -> bool:
        # 叛徒吸血鬼进教堂/圣徽房：硬阻挡（原文 6+ 可硬闯，校准简化）
        if not self._is_vampire_player(engine, player):
            return False
        if getattr(room, "template_id", getattr(room, "id", "")) == "chapel":
            return True
        key = getattr(room, "key", None)
        if key is None:
            return False
        return any(
            p.role == "hero" and not p.dead and "omen_holy_symbol" in p.items
            and p.room_key == key
            for p in engine.state.players
        )

    # --------------------------------------------------------- 怪物回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        tid = _monster_id(monster)
        if tid not in self.VAMPIRE_MONSTERS:
            return False
        if monster.id in self._unconscious_ids(engine):
            return True  # 昏迷不醒：不移动不攻击（仍可被钉杀）
        room = engine.state.board.get(monster.room_key)
        if (
            engine._haunt_flags().get("sunrise")
            and room is not None
            and room.template_id in self.SUNLIT_ROOMS
        ):
            self._destroy_vampire(
                engine, monster, None,
                f"阳光灌进{room.name}——{monster.name} 尖啸着燃烧殆尽！",
            )
            return True
        if tid == self.DRACULA and engine._haunt_track_value("sun_track") < 2:
            return True  # p112：德古拉第 2 回合前不移动不攻击（仍可防御）
        self._vampire_turn(engine, monster)
        return True

    def _vampire_turn(self, engine: Any, monster: Any) -> None:
        target = engine._find_monster_target(monster)
        if target is None:
            return
        # 移动：沿最短路径逐房判圣物准入（p112）
        path = engine._shortest_path(monster.room_key, target.room_key)
        steps = engine.roll_dice(max(1, monster.speed), "吸血鬼移动")
        moved = 0
        for nxt in path[1:]:
            if moved >= steps:
                break
            if self._holy_blocked(engine, monster, nxt):
                break
            monster.room_key = nxt
            moved += 1
        if moved:
            engine._log(f"{monster.name} 移动到 {engine.state.board[monster.room_key].name}。")
        # 同房间：普通力量攻击（引擎默认结算口径）
        if monster.room_key == target.room_key:
            attack_roll = engine._roll_monster_attack(monster, "might")
            target_roll = engine._roll_attack(target, "might")
            engine._log(f"{monster.name} 攻击 {target.name}：{attack_roll} 对 {target_roll}。")
            if attack_roll > target_roll:
                engine._deal_damage(target, "physical", attack_roll - target_roll, source=monster.name)
            elif attack_roll < target_roll:
                engine._stun_monster(monster, 1)
            else:
                engine._log("平手。")
            return
        # 隔门邻室：魅惑攻击（p112，理智对决）
        if target.room_key in set(engine._door_neighbors(monster.room_key)):
            attack_roll = engine._roll_monster_attack(monster, "sanity")
            target_roll = engine._roll_attack(target, "sanity")
            engine._log(f"{monster.name} 对 {target.name} 发动魅惑：{attack_roll} 对 {target_roll}。")
            if attack_roll > target_roll:
                diff = attack_roll - target_roll
                engine._apply_stat_loss(target, "speed", diff)
                engine._log(f"魅惑生效——{target.name} 受到 {diff} 点速度伤害。")
                target.room_key = monster.room_key
                engine._log(f"{target.name} 被拖进了{monster.name}所在的房间。")
                if target.stats["speed"] <= 0 and not target.dead:
                    self._vampirize(engine, target)
            elif attack_roll < target_roll:
                engine._log("魅惑被挣脱了——吸血鬼没有受伤（p112）。")
            else:
                engine._log("平手。")

    def _vampirize(self, engine: Any, player: Any) -> None:
        """p112：速度被魅惑打到见底 → 变成吸血鬼，转投叛徒方。"""
        if player.dead or self._is_vampire_player(engine, player):
            return
        self._mark_vampire(engine, player)
        player.role = "traitor"  # 复用引擎/bot 的阵营逻辑（同剧本 6 精神控制口径）
        face = engine.catalog.characters.get(player.character_id)
        for stat in ("might", "speed", "sanity", "knowledge"):
            track = engine._stat_track(player, stat)
            start = face.stats.get(stat) if face else None
            if start is not None and track is not None:
                idx = next((i for i, v in enumerate(track) if v >= start), len(track) - 1)
                player.stat_positions[stat] = idx
                player.stats[stat] = track[idx]
            target_value = player.stats[stat] + 1
            if track is not None:
                idx = next((i for i, v in enumerate(track) if v >= target_value), len(track) - 1)
                player.stat_positions[stat] = idx
                player.stats[stat] = track[idx]
            else:
                player.stats[stat] = player.stats[stat] + 1
        engine._log(f"{player.name} 的速度被吸到了尽头——他变成了吸血鬼，转而为德古拉效力！")
        engine.check_victory()

    def _mark_vampire(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        vampires = {str(i) for i in flags.get("vampire_ids", [])}
        vampires.add(str(player.id))
        flags["vampire_ids"] = sorted(vampires)

    # --------------------------------------------------- 英雄杀法（p41）
    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        tid = _monster_id(monster)
        if tid not in self.VAMPIRE_MONSTERS:
            return False
        # p41：长矛 + 力量攻击击败吸血鬼 = 钉杀
        if weapon_id == "omen_spear" and attack_attr == "might":
            self._destroy_vampire(
                engine, monster, attacker,
                f"{getattr(attacker, 'name', '探险者')} 把长矛钉进了{monster.name}的心脏！",
            )
            return True
        self._defeat_ctx = (str(getattr(attacker, "id", "")),)
        return False  # 其它成功攻击照常伤害/击晕

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        ctx = self._defeat_ctx
        self._defeat_ctx = None
        if _monster_id(monster) in self.VAMPIRE_MONSTERS and ctx is not None:
            attacker_id = ctx[0]
            attacker = next(
                (p for p in engine.state.players if str(p.id) == attacker_id), None
            )
            # p41：持圣徽者击败吸血鬼 → 按伤害点数沿门击退
            if attacker is not None and "omen_holy_symbol" in attacker.items and amount > 0:
                current = monster.room_key
                dist = engine._path_length(attacker.room_key, current)
                moved = 0
                while moved < amount:
                    neighbors = [
                        n for n in engine._door_neighbors(current)
                        if n != current and not engine._is_collapsed(n)
                    ]
                    if not neighbors:
                        break
                    best = sorted(
                        neighbors,
                        key=lambda k: (-engine._path_length(attacker.room_key, k), k),
                    )[0]
                    best_dist = engine._path_length(attacker.room_key, best)
                    if best_dist <= dist:
                        break
                    current = best
                    dist = best_dist
                    moved += 1
                if moved:
                    monster.room_key = current
                    engine._log(
                        f"圣徽放出光辉——{monster.name} 被{attacker.name}击退了 {moved} 个房间。"
                    )
        return False  # 照常击晕

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        if not actions:
            return actions
        unconscious = self._unconscious_ids(engine)
        result = []
        for action in actions:
            if action.id == "stake_unconscious":
                targets = [
                    m
                    for m in self._vampire_monsters(engine)
                    if m.id in unconscious and m.room_key == player.room_key
                ]
                if not targets:
                    continue  # 房间里没有昏迷的吸血鬼
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id != "stake_unconscious":
            return super().perform_action(engine, player, action_id, data)
        unconscious = self._unconscious_ids(engine)
        target = next(
            (
                m
                for m in self._vampire_monsters(engine)
                if m.id in unconscious and m.room_key == player.room_key
            ),
            None,
        )
        if target is None:
            return False
        self._destroy_vampire(
            engine, target, player,
            f"{player.name} 把木桩对准昏迷的{target.name}，狠狠钉了下去（p41）！",
        )
        return True

    # ------------------------------------------------------------ bot
    def _best_melee_dice(self, engine: Any, player: Any) -> int:
        """这名英雄用最趁手的近战武器能掷几枚骰（力量 + 武器加成）。"""
        might = int((getattr(player, "stats", {}) or {}).get("might", 0))
        best = might
        for card_id in getattr(player, "items", []):
            card = engine.catalog.cards.get(card_id)
            if card is None or "weapon" not in card.tags or "ranged" in card.tags:
                continue
            best = max(best, might + int((card.bonus or {}).get("attack", 0)))
        return best

    def _has_ranged_weapon(self, engine: Any, player: Any) -> bool:
        for card_id in getattr(player, "items", []):
            card = engine.catalog.cards.get(card_id)
            if card is not None and "weapon" in card.tags and "ranged" in card.tags:
                return True
        return False

    def bot_attack_blocked(self, engine: Any, player: Any, target: Any) -> bool:
        """英雄不去送死：大概率打不过的吸血鬼就别出手（p20 落败吃差值反击）。

        实测（30 局）：英雄对吸血鬼发起 195 次攻击、其中 55 次直接把英雄打死，
        占全部英雄死亡的一半以上——没长矛、力 2-4 的英雄去捶力 8 的德古拉，
        掷 1-3 骰对 8 骰，落败就是 5-7 点物理伤害。真人的打法：先躲，等日出
        把它每项属性磨下来（每个叛徒回合 -1）、或圣徽把它逼退击晕，打得过
        再用长矛补刀；昏迷的直接钉杀（另走剧本行动，不经过攻击）。
        """
        if player.role != "hero":
            return False
        if _monster_id(target) not in self.VAMPIRE_MONSTERS:
            return False
        if target.id in self._unconscious_ids(engine):
            return False  # 昏迷：该走钉杀行动，不是攻击（由 available_actions 引导）
        if getattr(target, "stunned_turns", 0) > 0:
            return False  # 被击晕：白送的输出窗口
        if self._has_ranged_weapon(engine, player):
            return False  # p20：远程攻击落败不受伤，可以放手打
        return self._best_melee_dice(engine, player) < int(getattr(target, "might", 0))

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """英雄 bot 的目标：只去"能赢"的吸血鬼。

        画像已关掉通用追怪（`attack_monsters: False`）——力 8 的德古拉追着打
        就是送死。这里只给两类目标：
          ① 有吸血鬼昏迷不醒 → 去同房钉杀（p41，免费摧毁，不需要掷骰）；
          ② 打得过（近战骰数 ≥ 它的力量，或它被击晕/自己有远程武器）→ 去补
             长矛那一刀（p41：长矛 + 力量攻击击败 = 钉杀）。
        打不过就不给目标：通用走位会把人留在远离吸血鬼的房间里拖到日出。
        """
        if player.role != "hero" or player.dead:
            return []
        vampires = self._vampire_monsters(engine)
        unconscious = self._unconscious_ids(engine)
        for monster in vampires:
            if monster.id in unconscious:
                return ["__room__" + monster.room_key]
        for monster in vampires:
            if self.bot_attack_blocked(engine, player, monster):
                continue
            return ["__room__" + monster.room_key]
        return []

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p41 英雄胜：德古拉与新娘都被摧毁
        if flags.get("dracula_destroyed") and flags.get("bride_destroyed"):
            engine._set_winner("heroes", "木桩与阳光终结了吸血鬼——德古拉只剩一个传说。")
            return True
        # p112 叛徒胜：所有英雄死亡或变成吸血鬼（角色已转阵营，不再是 hero）
        heroes = [p for p in engine.state.players if p.role == "hero"]
        if heroes and all(p.dead for p in heroes):
            engine._set_winner("traitor", "最后的英雄倒下了——夜幕将永远笼罩这座房子。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：叛徒死后吸血鬼照常行动
