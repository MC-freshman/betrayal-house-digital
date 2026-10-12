"""AI 模块的单向依赖；引擎不导入 AI。"""
from contextlib import contextmanager
from typing import Iterator
try:
    from ..engine import ActionCommand, AutoDecisionProvider, ExitOption, GameEngine
    from ..models import Monster, Player, STAT_NAMES
    from ..haunt_ai_profiles import get_haunt_ai_profile
except ImportError:  # direct script execution
    from engine import ActionCommand, AutoDecisionProvider, ExitOption, GameEngine
    from models import Monster, Player, STAT_NAMES
    from haunt_ai_profiles import get_haunt_ai_profile
