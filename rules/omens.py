"""H3：读牌后、投骰前的叛徒选择与显式卡面参数结算。"""


class OmenRules:
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
