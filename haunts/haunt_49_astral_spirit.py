"""AstralSpiritMode（剧本 49）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class AstralSpiritMode(GenericModeHandler):
    """剧本 49「You Wear It Well」（英雄手册 p60 / 叛徒手册 p131）。

    星界灵把所有英雄的灵魂拽出了肉体：英雄们以灵体状态继续行动，
    肉体昏迷在原地。星界灵想要一具"外套"——只要它附身一具无魂的
    肉体，或者把所有灵魂磨灭，英雄们就再也回不去了。

    · 开局（p130/p131）：星界灵放叛徒所在房间；英雄们的肉体昏迷
      （电子版把"灵魂"与"昏迷肉体"建在同一位英雄身上——位置即
      肉体位置，玩家继续扮演自己的灵魂，无需灵魂令牌）。
    · 灵魂规则（p60，保真部分）：英雄保留全部属性；不能探索新房间
      （can_discover_rooms 拦下）；攻击与防御只能用知识/理智
      （attack_attr_override 把力量/速度攻击覆盖为理智/知识中较高者）；
      攻击星界灵失败不受伤（attack_loss_damage_disabled）。
    · 摧毁星界灵（p60）：英雄攻击成功 → 不造成伤害，改为 +1 枚驱逐
      令牌（星界灵不晕不死，on_monster_defeated 全权处理）；累计到
      玩家数枚 → 星界灵被摧毁，英雄胜，众人回到肉体。
    · 星界灵攻击（p131）：只能以知识攻击英雄灵魂（on_monster_turn_attack
      接管为知识对决，差值即精神伤害；被击败则什么都不发生）。
    · 毁灭灵魂（p131）：叛徒攻击英雄（昏迷肉体）——电子版简化为标准
      攻击对决（原版无防御固定 2 骰精神伤）；精神属性被打到骷髅 =
      灵魂被毁，该英雄出局，其肉体进入"无魂"名单——**那正是星界灵
      尝试附身的目标**（p131 "the Astral Spirit can attempt a ritual
      to enter that hero's soulless body"）。
    · 附身仪式（p131）：星界灵回合移向最近的无魂肉体，同房间做理智
      检定，结果须**高于**该探索者的起始理智；每次成功 +1 枚附身令牌，
      累计到玩家数 → 附身成功，叛徒胜。
    · 胜负（p60/p131）：英雄胜 = 摧毁星界灵；叛徒胜 = 全部灵魂被毁，
      或星界灵附身一具无魂肉体。叛徒被杀而星界灵还在时星界灵继续
      行动（7/8 号怪物自主口径），故吸收兜底。

    已知简化：
        · 灵魂与星界灵的"穿墙移动"未建模——引擎移动基于门图，两者
          沿用正常移动；灵魂本就不能探索新房间，活动范围即已探明区域。
        · 灵魂与昏迷肉体同位建模（无独立灵魂令牌）；"灵魂被毁物品
          同毁"由引擎死亡掉落流程近似。
        · 「地下室与房屋断开时补楼梯」未建模（bot 局地下室通常已连通）。
        · 叛徒攻击昏迷肉体简化为标准对决（原版无防御固定 2 骰精神伤）；
          灵魂"物理伤害转精神伤害"、物品禁用（武器/Skull/玩具猴）、
          物品不可转移均未在物品系统层拦截（bot 不会主动违例）。
        · 「精神攻击击败叛徒则击晕」未建模（引擎玩家间攻击为标准对决）。
        · 附身检定的"起始理智"用角色属性轨道上限近似（引擎不单独记
          作祟时刻的初始值）。
    """

    mode = "astral_spirit"

    SPIRIT = "astral_spirit"
    MENTAL = ("sanity", "knowledge")

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("spirit_destroyed", False)
        flags.setdefault("spirit_inhabited", False)
        flags.setdefault("soulless", {})
        players = len(engine.state.players)
        engine._haunt_tracks().setdefault(
            "banish_tokens",
            {"label": "驱逐星界灵", "target": players, "value": 0},
        )["target"] = players

        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.SPIRIT, {"template_id": self.SPIRIT, "name": "星界灵"})
        )
        engine._spawn_single_haunt_monster(spec, traitor.room_key if traitor else room_key)
        engine._log(
            "一阵狂风撕开了所有人的灵魂——英雄们瘫倒在地，灵体在原地颤抖着站起。"
        )

    # ------------------------------------------------------- 灵魂规则
    def can_discover_rooms(self, engine: Any, player: Any) -> bool:
        """p60：灵魂不能探索新房间（叛徒不受影响）。"""
        if player.role == "hero":
            return False
        return True

    def attack_attr_override(
        self, engine: Any, attacker: Any, target: Any, default_attr: str
    ) -> str | None:
        """p60：灵魂攻击/防御只能用知识或理智。"""
        if getattr(attacker, "role", "") != "hero":
            return None
        if default_attr in ("might", "speed"):
            return "sanity" if attacker.stats.get("sanity", 0) >= attacker.stats.get(
                "knowledge", 0
            ) else "knowledge"
        return None

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p60：攻击星界灵失败不受伤。"""
        return getattr(target, "template_id", "") == self.SPIRIT

    def on_player_died(self, engine: Any, player: Any) -> None:
        """p131：灵魂被毁的英雄出局，其肉体进入无魂名单（星界灵会尝试附身它）。"""
        if player.role != "hero":
            return
        flags = engine._haunt_flags()
        soulless = dict(flags.get("soulless", {}))
        soulless[str(player.id)] = {
            "room_key": player.room_key,
            "ritual": 0,
            "starting_sanity": int(player.stats_max.get("sanity", 4)),
        }
        flags["soulless"] = soulless
        engine._log(f"{player.name} 的灵魂彻底消散了——那具肉体成了一具空壳。")

    # ------------------------------------------------------- 星界灵回合
    def _spirit(self, engine: Any) -> Any:
        return next(
            (m for m in engine.state.monsters if m.template_id == self.SPIRIT), None
        )

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if getattr(monster, "template_id", "") != self.SPIRIT:
            return False
        flags = engine._haunt_flags()
        players = len(engine.state.players)
        soulless = dict(flags.get("soulless", {}))
        pending = [
            (hid, info)
            for hid, info in soulless.items()
            if int(info.get("ritual", 0)) < players and info.get("room_key") in engine.state.board
        ]
        if not pending:
            return False  # 没有附身目标：走默认移动与攻击
        # p131：星界灵移向最近的无魂肉体
        target_room = min(
            (info["room_key"] for _, info in pending),
            key=lambda k: engine._path_length(monster.room_key, k),
        )
        path = engine._shortest_path(monster.room_key, target_room)
        if len(path) > 1:
            steps = max(1, engine.roll_dice(monster.speed, "星界灵移动"))
            monster.room_key = path[min(len(path) - 1, steps)]
        engine._log(f"星界灵飘到了{engine.state.board[monster.room_key].name}。")
        # 同房间做附身仪式（每回合一次理智检定，结果须高于起始理智）
        for hid, info in pending:
            if info["room_key"] != monster.room_key:
                continue
            roll = engine.roll_dice(monster.sanity, "附身仪式")
            threshold = int(info.get("starting_sanity", 4))
            engine._log(
                f"附身仪式：掷出 {roll}（需高于 {threshold}）。"
            )
            if roll > threshold:
                info["ritual"] = int(info.get("ritual", 0)) + 1
                soulless[hid] = info
                flags["soulless"] = soulless
                engine._log(
                    f"星界灵在这具空壳上又刻下了一道印记"
                    f"（{info['ritual']}/{players}）。"
                )
                if info["ritual"] >= players:
                    flags["spirit_inhabited"] = True
            else:
                soulless[hid] = info
                flags["soulless"] = soulless
            break  # 每回合只对一具肉体尝试
        return False  # 继续默认移动/攻击活英雄

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p131：星界灵只能以知识攻击英雄的灵魂（精神伤害）。"""
        if getattr(monster, "template_id", "") != self.SPIRIT:
            return False
        target = engine._find_monster_target(monster)
        if target is None or target.room_key != monster.room_key:
            return True  # 不同房就不攻击（也不能攻击肉体）
        roll = engine._roll_monster_attack(monster, "knowledge")
        defense = engine._roll_attack(target, "knowledge")
        engine._log(f"星界灵以精神利刃刺向 {engine._player_label(target)}：{roll} 对 {defense}。")
        if roll > defense:
            engine._deal_damage(target, "mental", roll - defense, source="星界灵")
        elif roll < defense:
            engine._log("灵体挣脱了它的触碰——星界灵毫发无损（p131：被击败不晕）。")
        return True

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p60：星界灵不晕不死——攻击成功改为累积驱逐令牌。"""
        if getattr(monster, "template_id", "") != self.SPIRIT:
            return False
        flags = engine._haunt_flags()
        engine._advance_haunt_track("banish_tokens")
        current = engine._haunt_track_value("banish_tokens")
        needed = engine._haunt_track_target("banish_tokens")
        engine._log(
            f"英雄们的精神攻击撼动了星界灵（{current}/{needed}）——它没有受伤，但被削弱了。"
        )
        if current >= needed > 0:
            flags["spirit_destroyed"] = True
        return True  # 不击晕、不默认离场

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p60：星界灵被摧毁 → 英雄胜，众人回到肉体
        if flags.get("spirit_destroyed"):
            engine._set_winner("heroes", "星界灵在齐心合力的精神攻击下灰飞烟灭——灵魂归位。")
            return True
        # p131：附身一具无魂肉体 → 叛徒胜
        if flags.get("spirit_inhabited"):
            engine._set_winner("traitor", "星界灵穿上了朋友的肉体——“你穿得很好。”")
            return True
        # p131：所有灵魂被毁 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "最后一位英雄的灵魂也熄灭了。")
            return True
        # 吸收兜底：叛徒被杀而星界灵还在——星界灵继续行动（7/8 号口径）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        spirit = self._spirit(engine)
        return [f"__room__{spirit.room_key}"] if spirit is not None else []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = [
            f"驱逐进度：{engine._haunt_track_value('banish_tokens')}/"
            f"{engine._haunt_track_target('banish_tokens')}。",
        ]
        soulless = flags.get("soulless", {})
        if soulless:
            marks = ", ".join(
                f"{info.get('ritual', 0)}枚" for info in soulless.values()
            )
            lines.append(f"无魂肉体：{len(soulless)} 具（附身印记 {marks}）。")
        return lines
