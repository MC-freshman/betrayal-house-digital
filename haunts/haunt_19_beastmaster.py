"""BeastmasterMode（剧本 19）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class BeastmasterMode(GenericModeHandler):
    """剧本 19 驯兽师（The Beastmaster）。

    权威原文：英雄手册 p30 / 叛徒手册 p101。

    · 叛徒即驯兽师，开局持有长矛（项目无矛卡，用令牌承载——与剧本 15
      同一处理）。五只动物随从按 p101 顺序布点：熊在任一其他探险者所在
      房间；狼进门厅（6 人局两只）；鳄鱼进地下湖或地下室门厅；鼬进
      花园/墓地/阳台否则叛徒房间；鹰进阳台/塔楼/朝外窗房间，都没有则
      不出现。项目没有动物模板，熊/鳄鱼/鼬/鹰分别用 beast/giant/cat/
      cat 模板承载，种类映射存 flags["beast_kind"]（engine_note 惯例）。
    · 英雄胜（p30）：用力量攻击或持戒指的理智攻击对驯兽师造成 **>2 点**
      伤害并改为偷走长矛（引擎新钩子 special_steal）——驯兽师恢复神智。
      attack_attr_override 本版起对玩家目标同样生效（默认 None），
      支持持戒理智攻击。
    · 杀死驯兽师 = 英雄失败（p30 "If you kill the Beastmaster, you
      lose"）——check_victory 显式判叛徒胜，必须避开引擎"叛徒死亡→
      英雄胜"兜底（本剧本最大的坑）。
    · 动物随从被击败即杀死（非击晕，p101）；熊主动攻击 +2、鳄鱼 +1
      （引擎读取 monster_specs 的 initiate_bonus，被攻击时不加）。
    · 已知简化：驯兽师开局的一次传送未实现（可选能力，bot 放弃）；
      长矛被偷后随从是否溃散原文未述，不影响胜负判定。
    """

    mode = "beastmaster"

    BEASTS = {
        "bear": ("beast", "熊", (3, 5, 4)),
        "wolf": ("wolf", "狼", (4, 5, 4)),
        "crocodile": ("giant", "鳄鱼", (2, 5, 4)),
        "weasel": ("cat", "鼬", (5, 2, 6)),
        "hawk": ("cat", "鹰", (5, 3, 5)),
    }
    WINDOW_ROOMS = ["grand_staircase", "master_bedroom", "bedroom", "chapel", "dining_room"]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["beast_kind"] = {}
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is None:
            return
        # 长矛 = 预兆牌 omen_spear（p101 "the spear you found"），在驯兽师手上
        # （英雄的目标）——与剧本 15 统一走真卡；英雄用 special_steal 夺走它。
        engine._grant_card_to_player(traitor, "omen_spear")

        spec_source = haunt.rule_data.get("monsters", [])
        players = len(engine.state.players)

        def spawn_beast(kind: str, room_key_target: str) -> None:
            template_id, name, stats = self.BEASTS[kind]
            spec = next((s for s in spec_source if s.get("template_id") == template_id), {})
            spec = dict(spec)
            spec["name"] = name
            spec["speed"], spec["might"], spec["sanity"] = stats
            monster = engine._spawn_single_haunt_monster(spec, room_key_target)
            if monster is not None:
                flags["beast_kind"][str(monster.id)] = kind

        # 熊：任一其他探险者所在房间（取第一个非叛徒活人）
        other = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
        if other is not None:
            spawn_beast("bear", other.room_key)
        # 狼：门厅（6 人局两只）
        entrance = next(
            (k for k, r in engine.state.board.items() if r.template_id == "entrance_hall"),
            room_key,
        )
        spawn_beast("wolf", entrance)
        if players >= 6:
            spawn_beast("wolf", entrance)
        # 鳄鱼：地下湖或地下室门厅
        croc_room = next(
            (k for k, r in engine.state.board.items() if r.template_id == "underground_lake"),
            None,
        ) or next(
            (k for k, r in engine.state.board.items() if r.template_id == "basement_landing"),
            room_key,
        )
        spawn_beast("crocodile", croc_room)
        # 鼬：花园/墓地/阳台，否则叛徒房间
        weasel_room = next(
            (
                k for k, r in engine.state.board.items()
                if r.template_id in ("garden", "graveyard", "patio")
            ),
            None,
        )
        spawn_beast("weasel", weasel_room or traitor.room_key)
        # 鹰：阳台/塔楼/朝外窗房间；都没有则不出现
        hawk_room = next(
            (
                k for k, r in engine.state.board.items()
                if r.template_id in ("balcony", "tower", *self.WINDOW_ROOMS)
            ),
            None,
        )
        if hawk_room is not None:
            spawn_beast("hawk", hawk_room)
        engine._log("驯兽师的嚎叫在房子里回荡——他的野兽们饿了。")

    # ------------------------------------------------------------- 内部
    def _kind_of(self, engine: Any, monster: Any) -> str:
        return str(engine._haunt_flags().get("beast_kind", {}).get(str(getattr(monster, "id", "")), ""))

    def _spear_holder(self, engine: Any) -> Any | None:
        """当前握有长矛（omen_spear 卡）的玩家。"""
        return next((p for p in engine.state.players if "omen_spear" in p.items), None)

    # ------------------------------------------------------------- 攻击规则
    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        """p30：持戒指者对驯兽师的徒手攻击改为理智攻击（对随从不变）。"""
        target_is_beastmaster = (
            isinstance(getattr(target, "role", None), str) and target.role == "traitor"
        )
        if target_is_beastmaster and default_attr == "might" and "omen_ring" in attacker.items:
            return "sanity"
        return None

    def special_steal(self, engine: Any, attacker: Any, target: Any, diff: int, attack_attr: str) -> bool:
        """p30：>2 点伤害改为偷走长矛——英雄的胜利条件。"""
        if getattr(target, "role", None) != "traitor":
            return False
        if attack_attr not in ("might",) and not (
            attack_attr == "sanity" and "omen_ring" in attacker.items
        ):
            return False
        spear = self._spear_holder(engine)
        if spear is None or spear is not target:
            return False
        engine._grant_card_to_player(attacker, "omen_spear")
        engine._haunt_flags()["spear_stolen"] = True
        engine._log(f"{attacker.name} 夺下了长矛——驯兽师的眼里恢复了神智！")
        return True

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p101：动物随从被击败即杀死（非击晕）。"""
        if not self._kind_of(engine, monster):
            return False
        monster_id = getattr(monster, "id", None)
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
        ]
        engine._advance_haunt_track("minions_slain", 1)
        engine._log(f"{monster.name} 被击毙了。")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        if flags.get("spear_stolen"):
            engine._set_winner("heroes", "长矛回到了凡人之手——驯兽师倒下了，你的朋友醒了过来。")
            return True
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and traitor.dead:
            # p30："If you kill the Beastmaster, you lose." —— 杀死驯兽师
            # 是英雄的失败条件，必须盖过引擎"叛徒死亡→英雄胜"兜底。
            engine._set_winner("traitor", "驯兽师死了，可长矛的诅咒仍在——你输了。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "野兽们的嚎叫吞没了最后的探险者。")
            return True
        return False
