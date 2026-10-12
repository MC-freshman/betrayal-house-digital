"""ZombieLordMode（剧本 21）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class ZombieLordMode(GenericModeHandler):
    """剧本 21 活死人之屋（House of the Living Dead）。

    权威原文：英雄手册 p32 / 叛徒手册 p103。

    已按原文实现：
        · 数值：僵尸 Speed 2 / Might 5 / Sanity 2；僵尸领主 Speed 3 / Might 7 /
          Sanity 2（p103 页脚）。
        · 叛徒开局即死：掉落全部物品，人物由僵尸领主令牌（大）顶替（p103
          "Your explorer is dead. Drop all your items and replace your
          character's figure with the Zombie Lord token"）。
        · 布点：先放「玩家数」枚僵尸令牌，按 地窖→墓地→门厅→地下湖→花园→
          教堂→温室→五芒星室 的顺序放进**已发现**的那些房间；房间不够就在
          同一间叠放；放完后再给每间已有僵尸的房间补放一只（p103）。
        · 杀死僵尸必须用"需要力量的武器"或炸药；其他攻击只把它打晕；
          僵尸免疫左轮（p32）。徒手力量攻击不算武器，所以仍只击晕。
        · 僵尸领主：只有持徽章者能伤到它，且持徽章者徒手也能打；它不吃
          击晕，累计 7 点伤害才倒，伤害不减属性（p32/p103，走 lord_damage 轨道）。
        · 圣徽：对持有者发动力量攻击的僵尸少掷两枚骰，对领主无效（p32）。
        · 英雄被杀 → 在自己倒下的房间里转化为一只新僵尸（p32/p103）。
        · 胜负：摧毁领主 或 消灭所有僵尸 → 英雄胜；英雄全灭 → 叛徒胜。
          叛徒开局就死，必须吸收引擎"叛徒死亡即英雄胜"的兜底（老坑第 6 次）。

    AI 目标（2026-10-12 修）：主攻手（quest_carrier）必须是持徽者本人——
    旧实现按"力量+武器加成"选主攻手，持徽者不是力量最高时会被派去护送，
    而主攻手打领主全部无效（attack_allowed 直接拒），33 局 lord_damage
    全 0 即此 bug 的实证。修复后徽章掉落后全员路由到徽章房、捡起者接管
    主攻（verify_haunt21_medallion_carrier 回归）。剩余 0 胜为战斗消耗
    层问题（每次命中差多少扣多少、领主反击约 3 点/回合，单主攻手打不满
    7 点），属 §11.33 已登记的 C 类 bot 战术专项，不是路由 bug。

    已知简化：
        · 转化的僵尸由引擎/bot 代跑，不由原玩家操控（p103 原版是"该玩家在自己
          的回合继续操控他的僵尸"）；因此"僵尸杀了英雄则该玩家也赢"的多胜方
          结算未建模。
        · p32「有机会抽物品卡时可抽三张选一张、其余放回牌堆底」未建模——引擎
          抽牌流程没有"多选一"的决策点，要 UI 与联机同时支持。
        · 僵尸不能用神秘电梯、领主可以：引擎的怪物从不触发电梯效果，天然满足。
        · 武器属性由卡牌 tags 推导，目前只有左轮标了 speed；原版的匕首类也是
          速度攻击，本仓库尚未给它们打标，所以在这里仍按力量武器算（会杀死
          僵尸）。本剧本只保证「左轮无效 / 力量武器命中即杀」两条原文判定。
    """

    mode = "zombie_lord"

    ZOMBIE = "zombie"
    LORD = "zombie_lord"
    DYNAMITE = "item_dynamite"
    MEDALLION = "omen_medallion"
    HOLY_SYMBOL = "omen_holy_symbol"
    # p103 的布点顺序
    PLACE_ORDER = (
        "crypt", "graveyard", "entrance_hall", "underground_lake",
        "garden", "chapel", "conservatory", "pentagram_chamber",
    )

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine._drop_inventory_on_death(traitor)
            traitor.dead = True
            engine._log(f"{traitor.name}被墙里伸出的灰白色手拖了进去——再站起来的东西不再是祂。")
        # 原表 #21 只由徽章触发（规则基准 p4），摘要抽本或强制试玩必须补此前置。
        if not engine._card_is_controlled(self.MEDALLION):
            revealer = next((p for p in engine.state.players
                             if p.id == engine.state.haunt_revealer_id and p.role == "hero" and not p.dead), None)
            holder = revealer or next(p for p in engine.state.players if p.role == "hero" and not p.dead)
            engine._grant_card_to_player(holder, self.MEDALLION)
            engine._log("活死人之屋的开局前置已补齐：英雄持有徽章。")
        placed = self._place_zombies(engine, room_key)
        engine._haunt_flags()["zombies_placed"] = placed
        engine._log(f"僵尸从墓穴与花园的方向围了过来（{placed} 只）。")

    def _zombie_spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.ZOMBIE) or {"template_id": self.ZOMBIE, "name": "僵尸"})

    def _place_zombies(self, engine: Any, haunt_room_key: str) -> int:
        """p103：玩家数枚僵尸按房间顺序布点，房不够则叠放，再给每间补一只。"""
        buckets: list[str] = []
        for template_id in self.PLACE_ORDER:
            for key, room in engine.state.board.items():
                if room.template_id == template_id and room.revealed:
                    buckets.append(key)
                    break
        if not buckets:
            buckets = [haunt_room_key]  # 列出的房间一间都没发现：退到作祟房
        spec = self._zombie_spec(engine)
        players = len(engine.state.players)
        first_pass = [buckets[index % len(buckets)] for index in range(players)]
        occupied = list(dict.fromkeys(first_pass))
        for room_key in first_pass + occupied:
            engine._spawn_single_haunt_monster(spec, room_key)
        return players + len(occupied)

    # ---------------------------------------------------------- 战斗规则
    bot_goal_exclusive = True
    REVOLVER = "item_revolver"

    def item_draw_choices(self, engine, player):
        return 3 if player.role == "hero" else 1

    def bot_item_draw_score(self, engine, player, card_id):
        card = engine.catalog.cards[card_id]
        if "weapon" in card.tags and card_id != self.REVOLVER:
            return 100 + 10 * engine._attack_bonus_from_inventory(player, card_id)
        return 40 if card.effect_id in {"item_heal_small", "item_heal_large"} else 0

    def bot_weapon_bonus(self, engine, player, target, weapon_id):
        if _monster_id(target) == self.LORD and self.MEDALLION in player.items:
            return 160
        if (_monster_id(target) == self.ZOMBIE and weapon_id
                and "weapon" in engine.catalog.cards[weapon_id].tags and weapon_id != self.REVOLVER):
            return 60
        return 0

    def quest_carrier(self, engine):
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return None
        # p32：只有持徽章者能伤到僵尸领主——主攻手必须是持徽者本人。
        # 旧实现按"力量+武器加成"选主攻手：持徽者若不是力量最高，会被派去
        # 护送主攻手，而主攻手打领主全部无效（attack_allowed 直接拒），
        # 33 局 lord_damage 全 0 正是这么来的（2026-10-12 探针实证）。
        holder = next((p for p in heroes if self.MEDALLION in p.items), None)
        if holder is not None:
            return holder.id
        def strength(hero):
            bonus = max([0] + [engine._attack_bonus_from_inventory(hero, card)
                              for card in hero.items if "weapon" in engine.catalog.cards[card].tags])
            return hero.stats.get("might", 0) + bonus, -hero.id
        return max(heroes, key=strength).id

    def bot_goal_rooms(self, engine, player):
        if player.dead or player.role != "hero":
            return []
        if self.MEDALLION in player.items:
            carrier_id = self.quest_carrier(engine)
            if player.id != carrier_id:
                carrier = next(p for p in engine.state.players if p.id == carrier_id)
                return ["__room__" + carrier.room_key]
            return ["__room__" + m.room_key for m in engine.state.monsters if _monster_id(m) == self.LORD]
        loose = ["__room__" + key for key, cards in engine.state.room_items.items() if self.MEDALLION in cards]
        if loose:
            return loose
        holder = next((p for p in engine.state.players if not p.dead and self.MEDALLION in p.items), None)
        if holder:
            return ["__room__" + holder.room_key]
        return []

    def bot_wants_explore(self, engine, player):
        return (player.role == "hero" and not any(self.MEDALLION in p.items for p in engine.state.players if not p.dead)
                and not any(self.MEDALLION in cards for cards in engine.state.room_items.values()))

    def _holds(self, player: Any, card_id: str) -> bool:
        return card_id in (getattr(player, "items", None) or [])

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p32：没有徽章的人攻击僵尸领主毫无效果（连击晕都不算）。"""
        if _monster_id(target) != self.LORD:
            return True
        return self._holds(attacker, self.MEDALLION)

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """p32：力量武器与炸药能杀死僵尸，其他攻击只能把它打晕。"""
        if _monster_id(monster) != self.ZOMBIE:
            return False
        if weapon_id == self.DYNAMITE:
            return True
        return bool(weapon_id) and attack_attr == "might"

    def monster_attack_roll_bonus(self, engine: Any, monster: Any, target: Any) -> int:
        """p32：圣徽持有者让僵尸的力量攻击少掷两枚骰（不影响僵尸领主）。"""
        if _monster_id(monster) != self.ZOMBIE:
            return 0
        if not self._holds(target, self.HOLY_SYMBOL):
            return 0
        return -2

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """僵尸领主：不吃击晕，累计 7 点伤害才倒（p103 用回合/伤害轨记录）。"""
        if _monster_id(monster) != self.LORD:
            return False
        engine._advance_haunt_track("lord_damage", max(1, amount))
        taken = engine._haunt_track_value("lord_damage")
        capacity = engine._haunt_track_target("lord_damage") or 7
        if taken >= capacity:
            engine._kill_monster(monster)
            engine.check_victory()
        else:
            engine._log(f"僵尸领主挨到第 {taken}/{capacity} 点伤害，只是晃了晃。")
        return True

    # -------------------------------------------------------------- 转化
    def on_player_died(self, engine: Any, player: Any) -> None:
        """p32：英雄被杀后变成僵尸（原版由其玩家下回合继续操控，见类注释）。"""
        if getattr(player, "role", "") != "hero":
            return
        flags = engine._haunt_flags()
        converted = set(flags.get("converted_ids", []) or [])
        if player.id in converted:
            return
        converted.add(player.id)
        flags["converted_ids"] = sorted(converted)
        zombie = engine._spawn_single_haunt_monster(self._zombie_spec(engine), player.room_key)
        if zombie is not None:
            engine._log(f"{player.name}又站了起来——饿着肚子的、灰白色皮肤的祂。")

    # ---------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "屋子里只剩下拖着的脚步声和咀嚼声。")
            return True
        alive = {_monster_id(monster) for monster in engine.state.monsters}
        if not engine._haunt_flags().get("zombies_placed"):
            return True  # setup 还没布点：此时"场上没僵尸"不代表被清空了
        if self.LORD not in alive:
            engine._set_winner("heroes", "僵尸领主散成一堆枯骨，围着的僵尸跟着一个个瘫了下去。")
            return True
        if self.ZOMBIE not in alive:
            engine._set_winner("heroes", "最后一只僵尸倒下，墙里的抓挠声终于停了。")
            return True
        return True  # 叛徒开局已死：吸收引擎"叛徒死亡即英雄胜"的兜底
