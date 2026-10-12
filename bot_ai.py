"""兼容入口；AI 决策实现按职责保存在 ai/。"""
if __package__:
    from .ai.controller import BotController
    from .ai.decisions import BotDecisionProvider, STAT_LABELS
else:
    from ai.controller import BotController
    from ai.decisions import BotDecisionProvider, STAT_LABELS

__all__ = ["BotController", "BotDecisionProvider", "STAT_LABELS"]
