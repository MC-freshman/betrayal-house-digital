from __future__ import annotations

from ._imports import AutoDecisionProvider, GameEngine, Player

STAT_LABELS = {
    "速度": "speed",
    "力量": "might",
    "理智": "sanity",
    "知识": "knowledge",
}

class BotDecisionProvider(AutoDecisionProvider):
    def __init__(self, engine: GameEngine, player: Player, human_prompter: object | None = None) -> None:
        self.engine = engine
        self.player = player
        self.human_prompter = human_prompter

    def confirm(self, title: str, message: str) -> bool:
        if title == "塌方房间":
            return False  # 默认放弃会受伤的主动坠落；首次发现的强制检定仍执行。
        if title == "盔甲" and self._message_mentions_human(message):
            return self.human_prompter.confirm(title, message) if self.human_prompter else True
        if title in {"偷窃", "重掷"}:
            return False
        if title == "盔甲":
            return True
        if title == "事件卡":
            return False
        return True

    def choose_from_list(self, title: str, message: str, options: list[str]) -> int | None:
        if not options:
            return None
        if title == "恢复属性":
            return self._choose_lowest_stat_option(options)
        if title == "远古护身符":
            return self._choose_lowest_stat_option(options)
        if title == "神秘电梯":
            return 0
        return 0

    def choose_rotation(
        self,
        title: str,
        message: str,
        placements: list[dict],
        entry_direction: str,
    ) -> int | None:
        if not placements:
            return None
        return max(range(len(placements)), key=lambda idx: len(placements[idx].get("doors", ())))

    def choose_split_damage(
        self,
        title: str,
        message: str,
        amount: int,
        first_label: str,
        second_label: str,
    ) -> int | None:
        if self._message_mentions_human(message):
            if self.human_prompter:
                return self.human_prompter.choose_split_damage(title, message, amount, first_label, second_label)
            return max(0, amount // 2)
        target = self._player_mentioned_in_message(message) or self.player
        first_stat = STAT_LABELS.get(first_label)
        second_stat = STAT_LABELS.get(second_label)
        if not first_stat or not second_stat:
            return max(0, amount // 2)
        def projected(stat, loss):
            track = self.engine._stat_track(target, stat)
            if track:
                reserve = target.stat_positions.get(stat, 0) + target.overflow.get(stat, 0) - loss
                pos = target.stat_positions.get(stat, 0) - max(0, loss - target.overflow.get(stat, 0))
                if self.engine.state.phase == "EXPLORE":
                    pos = max(0, pos)
                value = track[pos] if 0 <= pos < len(track) else 0
                return reserve, value
            value = max(0, target.stats.get(stat, 0) - loss)
            return value - 1, value

        def score(first_loss):
            a, av = projected(first_stat, first_loss)
            b, bv = projected(second_stat, amount - first_loss)
            # 属性数字不是剩余生命格；重复数字轨道尤其不能按数字大小分伤害。
            return (av > 0 and bv > 0, min(a, b), av + bv, -abs(2 * first_loss - amount))

        return max(range(amount + 1), key=score)

    def _choose_lowest_stat_option(self, options: list[str]) -> int:
        best_index = 0
        best_value = 999
        for index, label in enumerate(options):
            stat = STAT_LABELS.get(label)
            if not stat:
                continue
            value = self.player.stats.get(stat, 0)
            if value < best_value:
                best_index = index
                best_value = value
        return best_index

    def _message_mentions_human(self, message: str) -> bool:
        return any(player.control == "human" and player.name in message for player in self.engine.state.players)

    def _player_mentioned_in_message(self, message: str) -> Player | None:
        return next((player for player in self.engine.state.players if player.name in message), None)
