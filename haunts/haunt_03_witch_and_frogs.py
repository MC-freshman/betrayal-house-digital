"""WitchAndFrogsMode（剧本 3）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class WitchAndFrogsMode(GenericModeHandler):
    """剧本 3 青蛙腿浓汤（Frog-Leg Stew）。

    权威原文：英雄手册 p14 / 叛徒手册 p85。

    已核对且原本就正确：女巫 Speed 4 / Might 3 / Sanity 6（门厅生成）、
    猫 Speed 3 / Might 3 / Sanity 2；挖根 Knowledge 4+、凡人形态 6+、
    复原 4+。

    本次补齐：
        · Root 令牌放置（温室/储藏室/厨房，未发现则发现时补放）与挖取/消耗
        · 女巫无敌真正生效（引擎此前从不读 invulnerable_until）
        · 女巫法术：蛙皮（同房间理智对决变蛙）、鸦翼（飞向最近英雄）、
          龙息（视野内或同房的英雄，2 骰不可防御物理伤害）
        · 青蛙状态：掉物品、力量/知识降到最低格（不降骷髅），
          不能攻击/抽牌/探索；复原时属性回到角色卡初始值
        · 蛙可被其他探险者像物品一样背起携带（p14）：背着走、放下、
          背着时什么都不能做；猫仍会追蛙
        · 猫：第一个蛙出现后生成于作祟房间，追最近的蛙，力量对决吃掉

    已知简化：
        · 背/放蛙在电子版占"剧本行动"（每人每回合一次），原版近似物品
          动作，行动经济略有出入；蛙被背着期间猫仍可能追上来把它吃掉。
        · 女巫每回合的法术选择用 bot 固定策略（同房优先蛙皮 → 视野内
          龙息 → 鸦翼追人），人类叛徒暂无逐回合自选法术的界面。
    """

    mode = "witch_and_frogs"

    ROOT_ROOMS = ("conservatory", "larder", "kitchen")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        # p85 原文设定："They have the Witch's spellbook (the Book card)."
        # 电子版必须主动保证这个前提：作祟之后探险者不再为探索而探索，预兆
        # 符号房间基本不再被发现，书会一直躺在预兆牌堆里，英雄永远施不出
        # 凡人形态、女巫永久无敌，整局卡死（seed=109 实测：400 回合后 11 张
        # 预兆牌一张都没被摸过）。所以书若还没出场，就交给一名英雄——
        # 这正是原文设定的状态。若书已被叛徒持有则保持（叛徒抢到了，
        # 英雄得去夺回）。
        if not engine._card_is_controlled("omen_book"):
            hero = next(
                (p for p in engine.state.players if p.role == "hero" and not p.dead),
                None,
            )
            if hero is not None and engine._grant_card_to_player(hero, "omen_book"):
                engine._log(f"女巫的魔法书一直在{hero.name}手上。")

        # p85：三株曼德拉草放温室/储藏室/厨房；未发现的房间等发现时再放，
        # 且不公开哪些未发现房间有草。
        # 但这些房间必须先真的在场上——作祟后探险者不再主动探索，房间可能
        # 整局都不出现，草也就一株都长不出来，剧本直接卡死。所以先把它们
        # 拉进屋子（原版 p84 对五芒星室有同样做法）。
        pending: list[str] = []
        for template_id in sorted(self.ROOT_ROOMS):
            room_key_now = engine._ensure_room_in_play(template_id, room_key)
            if room_key_now:
                engine.spawn_token("root", label="曼德拉草", role="marker", room_key=room_key_now)
            else:
                pending.append(template_id)
        engine._haunt_flags()["pending_roots"] = pending

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        flags = engine._haunt_flags()
        pending = list(flags.get("pending_roots", []))
        if room.template_id in pending:
            pending.remove(room.template_id)
            flags["pending_roots"] = pending
            engine.spawn_token("root", label="曼德拉草", role="marker", room_key=room.key)
            # p85："Don't announce which undiscovered rooms will get Root
            # tokens."——悄悄放下，不广播草的存在。

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        carried = self._carried_map(engine)
        result = []
        for action in actions:
            if action.id == "dig_root" and not engine.tokens_in_room(player.room_key, "root"):
                continue  # p14：只有在长着曼德拉草的房间才能挖
            if action.id == "cast_mortal_form" and not engine.tokens_held_by(player.id, "root"):
                continue  # 施法需要曼德拉草
            if action.id == "carry_frog":
                frog_here = any(
                    p.frog and not p.dead and p.id != player.id
                    and p.room_key == player.room_key
                    and str(p.id) not in carried
                    for p in engine.state.players
                )
                if player.frog or not frog_here or player.id in carried.values():
                    continue  # 蛙不能背蛙；房间里要有没人背着的蛙；一次背一只
            if action.id == "drop_frog":
                if player.id not in carried.values():
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "dig_root":
            if not engine.tokens_in_room(player.room_key, "root"):
                engine._log("这个房间里没有曼德拉草可挖。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            # super() 的返回值是"行动已执行"（检定失败也是 True），
            # 奖励必须按检定结果发。
            if engine.last_haunt_action_succeeded():
                root = next(iter(engine.tokens_in_room(player.room_key, "root")), None)
                if root:
                    engine.give_token(root.uid, player.id)
                    engine._log(f"{player.name} 挖出了一株曼德拉草。")
            return ok

        if action_id == "cast_mortal_form":
            if not engine.tokens_held_by(player.id, "root"):
                engine._log("施放凡人形态需要一株曼德拉草。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if engine.last_haunt_action_succeeded():
                # rule_data 的 set_flags 已置 witch_vulnerable；这里消耗草
                root = next(iter(engine.tokens_held_by(player.id, "root")), None)
                if root:
                    engine.remove_token(root.uid)
                engine._log("凡人形态生效——女巫的护盾消失了！")
            return ok

        if action_id == "restore_frog":
            frogs = [
                p
                for p in engine.state.players
                if p.frog and not p.dead and p.room_key == player.room_key
            ]
            if not frogs:
                engine._log("这个房间里没有青蛙。")
                return False
            # 必须自己判检定结果：super().perform_action 的返回值是"行动是否
            # 执行"，检定失败时它同样返回 True——照抄 old 写法会让"失败也复原
            # 青蛙"，等于把 p14 的 4+ 知识检定变成白送。
            if not engine._resolve_check(player, "knowledge", 4, "复原青蛙"):
                return True
            engine._restore_from_frog(frogs[0])
            self._sync_carried(engine)  # 复原的蛙解除"被背着"绑定
            return True

        if action_id == "carry_frog":
            carried = self._carried_map(engine)
            frog = next(
                (
                    p for p in engine.state.players
                    if p.frog and not p.dead and p.id != player.id
                    and p.room_key == player.room_key and str(p.id) not in carried
                ),
                None,
            )
            if frog is None or player.frog or player.id in carried.values():
                engine._log("这个房间里没有可背起的青蛙。")
                return False
            carried[str(frog.id)] = player.id
            engine._haunt_flags()["frog_carried"] = carried
            engine._log(f"{player.name} 把青蛙{frog.name}像行李一样背了起来。")
            return True

        if action_id == "drop_frog":
            carried = self._carried_map(engine)
            mine = [fid for fid, cid in carried.items() if cid == player.id]
            if not mine:
                engine._log("你没有背着青蛙。")
                return False
            carried.pop(mine[0], None)
            engine._haunt_flags()["frog_carried"] = carried
            frog = next((p for p in engine.state.players if str(p.id) == mine[0]), None)
            engine._log(f"{player.name} 把{frog.name if frog else '青蛙'}放了下来。")
            return True

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 女巫
    def _attackable_heroes(self, engine: Any) -> list[Any]:
        return [p for p in engine.state.players if p.role == "hero" and not p.dead and not p.frog]

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p14/p85：凡人形态生效后，任何成功攻击都直接杀死女巫。

        引擎默认只是击晕怪物，而剧本 3 的英雄胜利条件就是"杀死女巫"。
        没有这一步，即使施法成功，女巫也只是昏迷一回合又爬起来，
        整局会一直空转到回合上限（seed=109 实测）。
        """
        if _monster_id(monster) != "witch":
            return False
        if not engine._haunt_flags().get("witch_vulnerable"):
            # 还没施放凡人形态：原文明确"She can't be attacked"，
            # 引擎已挡下攻击，这里兜底仍按击晕处理。
            return False
        engine.state.monsters = [m for m in engine.state.monsters if m.id != monster.id]
        engine._log("女巫发出一声尖叫，化作尘埃消失了！")
        engine.check_victory()
        return True

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        if _monster_id(monster) == "witch":
            # p85：女巫不能普通攻击，同房间有英雄时改施蛙皮
            self._cast_skin_of_frog(engine, monster)
            return True
        if _monster_id(monster) == "cat":
            return True  # 猫只吃蛙，不吃英雄
        return False

    def _cast_skin_of_frog(self, engine: Any, witch: Any) -> None:
        heroes = [p for p in self._attackable_heroes(engine) if p.room_key == witch.room_key]
        if not heroes:
            return
        # p85：双方掷理智，女巫高则变蛙。机器人对第一个目标施放；
        # 人类叛徒选目标留待接 prompter（记为待办）。
        victim = heroes[0]
        witch_roll = engine._roll_monster_attack(witch, "sanity")
        hero_roll = engine._roll_attack(victim, "sanity")
        engine._log(f"女巫对{victim.name}施放蛙皮之咒：{witch_roll} 对 {hero_roll}。")
        if witch_roll > hero_roll:
            engine._turn_into_frog(victim)
        else:
            engine._log(f"{victim.name} 抵抗住了蛙皮之咒。")

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) == "witch":
            return self._witch_move(engine, monster)
        if _monster_id(monster) == "cat":
            return self._cat_move(engine, monster)
        return False

    def _witch_move(self, engine: Any, witch: Any) -> bool:
        # 同房间有正常英雄：原地留着施蛙皮
        if any(p.room_key == witch.room_key for p in self._attackable_heroes(engine)):
            return True
        # p85 龙息：视野内（无阻隔直线门道，可跨房间）没有同房目标时，
        # 对够远的可见英雄喷 2 骰不可防御的物理伤害。太近的英雄（≤3 格）
        # 不值得喷——女巫更愿意鸦翼贴脸施蛙皮（转化是叛徒的胜路，也让
        # 英雄有机会反击；实测全距离喷息会把局拖成英雄够不着的僵局）。
        visible = sorted(
            [
                p for p in self._attackable_heroes(engine)
                if p.room_key != witch.room_key
                and engine._has_line_of_sight(witch.room_key, p.room_key)
            ],
            key=lambda p: (engine._path_length(witch.room_key, p.room_key), p.id),
        )
        if visible and engine._path_length(witch.room_key, visible[0].room_key) > 3:
            victim = visible[0]
            amount = engine.roll_damage_dice(2, "龙息")
            engine._log(f"女巫向{victim.name}喷出龙息（2 骰不可防御物理伤害）！")
            engine._deal_damage(victim, "physical", amount, source="女巫的龙息")
            engine.check_victory()
            return True
        # 否则鸦翼：飞向最近的可施法英雄（p85 "Wings of Raven ... any room"）
        targets = sorted(
            self._attackable_heroes(engine),
            key=lambda p: (engine._path_length(witch.room_key, p.room_key), p.id),
        )
        if not targets:
            return True
        dest = targets[0].room_key
        if dest != witch.room_key:
            witch.room_key = dest
            engine._log(f"女巫振翅飞到了{engine.state.board[dest].name}。")
        return True

    # ------------------------------------------------------------- 背蛙
    # p14："Another explorer (who isn't a Frog) can pick up and carry a
    # Frog like an item. Frogs cannot do anything while being carried."
    # 绑定表 flags["frog_carried"] = {蛙玩家id(str): 背负者id}。
    # 近似说明：背/放蛙作为"剧本行动"占用本回合一次行动（原版近似物品
    # 动作，行动经济略有出入，已记录在类注释）。
    def _carried_map(self, engine: Any) -> dict:
        return engine._haunt_flags().setdefault("frog_carried", {})

    def _sync_carried(self, engine: Any) -> None:
        """蛙跟着背负者走；顺带清理失效绑定（背负者死/变蛙/蛙复原）。"""
        carried = self._carried_map(engine)
        players = {p.id: p for p in engine.state.players}
        changed = False
        for frog_id in list(carried):
            frog = players.get(int(frog_id))
            carrier = players.get(int(carried[frog_id]))
            if (
                frog is None or carrier is None or carrier.dead or frog.dead
                or not frog.frog or carrier.frog
            ):
                carried.pop(frog_id, None)
                changed = True
                continue
            if frog.room_key != carrier.room_key:
                frog.room_key = carrier.room_key
                changed = True
        if changed:
            engine._haunt_flags()["frog_carried"] = carried

    def on_player_moved(self, engine: Any, player: Any) -> None:
        self._sync_carried(engine)

    def _cat_move(self, engine: Any, cat: Any) -> bool:
        # p85：猫向最近的青蛙移动；同房间以力量对决，赢则吃掉。
        frogs = sorted(
            [p for p in engine.state.players if p.frog and not p.dead],
            key=lambda p: (engine._path_length(cat.room_key, p.room_key), p.id),
        )
        if not frogs:
            return True  # 没有蛙，猫趴着不动
        prey = frogs[0]
        if cat.room_key != prey.room_key:
            path = engine._shortest_path(cat.room_key, prey.room_key)
            if len(path) > 1:
                steps = max(1, engine.roll_dice(cat.speed, "猫的移动"))
                cat.room_key = path[min(len(path) - 1, steps)]
                engine._log(f"猫移动到{engine.state.board[cat.room_key].name}。")
        if cat.room_key == prey.room_key:
            cat_roll = engine._roll_monster_attack(cat, "might")
            frog_roll = engine._roll_attack(prey, "might")
            engine._log(f"猫扑向青蛙{prey.name}：{cat_roll} 对 {frog_roll}。")
            if cat_roll > frog_roll:
                prey.dead = True
                engine._log(f"猫把{prey.name}吃掉了！")
                engine.check_victory()
            else:
                engine._log("青蛙跳开了。")
        return True

    def on_turn_start(self, engine: Any, player: Any) -> None:
        self._sync_carried(engine)  # 清理失效的背蛙绑定（背负者死/变蛙等）
        # p85：第一个探险者变蛙时，猫出现在作祟揭示的房间。
        flags = engine._haunt_flags()
        if flags.get("cat_spawned"):
            return
        if not any(p.frog and not p.dead for p in engine.state.players):
            return
        flags["cat_spawned"] = True
        haunt_room = engine._haunt_rule_state().get("haunt_room")
        spec = engine._haunt_rule_state().get("monster_specs", {}).get("cat", {})
        if haunt_room and engine._spawn_single_haunt_monster(spec, haunt_room):
            engine.spawn_token("cat", label="猫", role="marker", room_key=haunt_room)
            engine._log("一只舔着爪子的猫出现在了作祟的房间里。")

    # ------------------------------------------------------------ bot
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """英雄的目标：凑齐「书 + 曼德拉草」，再去女巫房间施凡人形态（p14/p85）。

        实测（seed113-3p，批次6 黄金重建时暴露）：书被叛徒抢在手里时，通用
        目标换算只会给出"女巫所在房"（`cast_mortal_form` 的 same_room 要求）
        与挖草房——**没有任何目标指向书**（通用换算只在"关键牌掉在地上"时才
        引导去捡）。英雄拿着曼德拉草在女巫房干等，女巫永远不可攻击、叛徒又
        打不过他，对局 400 回合收不了场。真人这时会去找持书的人把书夺回来：
        书在谁手里是公开信息，攻击获胜即可偷取（引擎 `_steal_from_target`）。
        """
        if player.dead or player.role != "hero":
            return []
        if engine._haunt_flags().get("witch_vulnerable"):
            return []  # 凡人形态已生效：交给通用逻辑（去攻击女巫）
        if "omen_book" not in player.items:
            holder = next(
                (p for p in engine.state.players if not p.dead and "omen_book" in p.items),
                None,
            )
            if holder is not None:
                return ["__room__" + holder.room_key]
            floor = sorted(
                key for key, items in engine.state.room_items.items() if "omen_book" in items
            )
            if floor:
                return ["__room__" + key for key in floor]
        # 手里没草：去挖草房（还有草可挖时才去，避免草用光后原地打转）
        if not engine.tokens_held_by(player.id, "root") and engine.tokens_of_kind("root"):
            return ["conservatory", "larder", "kitchen", "entrance_hall"]
        witch = next((m for m in engine.state.monsters if _monster_id(m) == "witch"), None)
        if witch is not None:
            return ["__room__" + witch.room_key]
        return []

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        # p14：英雄胜利 = 杀死女巫
        if engine.state.haunt and engine._monster_by_template("witch") is None:
            engine._set_winner("heroes", "女巫被消灭了。")
            return True
        # p85：叛徒胜利 = 英雄全灭或全部变成青蛙
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if heroes and all(p.frog for p in heroes):
            engine._set_winner("traitor", "所有英雄都变成了青蛙。")
            return True
        if super().check_victory(engine):
            return True
        # p85 只规定女巫死/英雄全灭两种终局：杀死叛徒【不】构成英雄胜利
        # （女巫独立施法，会继续把英雄变蛙）。吸收通用兜底，游戏继续。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
