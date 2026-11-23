"""H3：读牌后、投骰前的叛徒选择与显式卡面参数结算。

咬伤（Bite）的攻击参数出处
--------------------------
仓库里的卡图（``photos/omen/omen_bite.png``）只有插画、印字框是空的；
``docs/BetrayalHouseHill_v4.2.pdf`` 只出现"叛徒可不受 Bite 影响"（p2）与各剧本对
Bite 卡的引用（p77/p85/p151），没有卡面数值。卡面文字取 2nd Edition 通行印字：

    "When you draw this card, something bites you. The player on your right
     rolls a might 4 attack against you ... You defend against this attack as
     normal by rolling dice equal to your might."

也就是一次 might 对抗：攻击方 4 枚骰，防守方按自己的 might 投骰，伤害按普通攻击
（攻击 - 防守）结算、属性为物理。除此之外不追加任何连锁规则。

数据优先级：卡对象自带且带 ``source`` 的 ``data["bite_attack"]`` 优先；缺失时由
:meth:`OmenRules._ensure_bite_attack` 在抽牌入口写入本默认值。
``_resolve_omen_effect`` 仍然保持"无数据即记缺口、不投骰"的 fail-closed 语义
（回归见 ``verify_ai_rules.test_bite_uses_explicit_data_and_missing_data_is_not_guessed``）。
"""

BITE_ATTACK = {
    "stat": "might",
    "dice": 4,
    "damage_type": "physical",
    "source": (
        "Betrayal 2nd Ed. Bite（咬伤）预兆卡面：对手以 might 4 攻击，"
        "抽牌者按自己的 might 正常防御，伤害按普通攻击结算"
    ),
}


class OmenRules:
    def _ensure_bite_attack(self, card) -> None:
        """抽牌入口：卡面没有印字数值时补入本规则层的默认攻击参数。

        只补缺（已有 ``bite_attack`` 的卡不被覆盖），因此剧本/测试注入的自定义
        数值仍然优先；不在这里结算，结算仍走 :meth:`_resolve_omen_effect`。
        """
        if getattr(card, "effect_id", None) != "omen_bite":
            return
        if card.data.get("bite_attack"):
            return
        card.data["bite_attack"] = dict(BITE_ATTACK)

    def _resolve_omen_effect(self, player, card):
        if card.effect_id != "omen_bite":
            return
        if player.role == "traitor" and self.prompter.confirm("咬伤预兆", "是否忽略这张预兆的影响？"):
            return
        data = card.data.get("bite_attack")
        if not data or not data.get("source"):
            self._log("[规则缺口] 咬伤的攻击数值尚缺对应版次的卡面资料。")
            return
        stat, dice, damage_type = data["stat"], data["dice"], data["damage_type"]
        if stat not in player.stats or not isinstance(dice, int) or dice < 0 or damage_type not in ("physical", "mental"):
            raise ValueError("咬伤卡面攻击参数无效")
        attack = self.roll_dice(dice, card.name)
        defense = self._roll_attack(player, stat)
        if attack > defense:
            self._deal_damage(player, damage_type, attack - defense, source=card.name)
