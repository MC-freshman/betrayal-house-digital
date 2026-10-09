"""剧本行为按 mode 分派。

背景
----
70 个剧本在 `haunt_rules.py` 里各有一个唯一 `mode`（werewolf_hunt、
labyrinth_escape、banishment_escort …）。但引擎原本是这样分派的：

    if self.state.haunt.id == 1:  return self._available_haunt1_actions(player)
    if self.state.haunt.id == 5:  return self._available_haunt5_actions(player)
    return self._available_generic_haunt_actions(player)

也就是说：mode 字段写在数据里、引擎从不读取，是死数据；剧本行为只能靠
在引擎里加 `haunt.id == N` 分支来扩展。严格复刻 70 个剧本时，这条路会
把 engine.py 撑爆，而且每加一个剧本都要改引擎。

本模块把分派改成按 mode 查表：
    注册了 handler 的 mode  → 走定制逻辑
    没注册的 mode           → 走 GenericModeHandler（现有通用规则）
这样新增剧本行为只需在这里加一个类，不必碰引擎。

设计约束
--------
* handler 用鸭子类型，不 import engine，避免循环导入。engine 在运行时
  才 import 本模块。
* 未注册的 mode 必须优雅降级到通用规则，绝不能抛异常——否则一个没写
  handler 的剧本就会让整个作祟阶段崩掉。
* 本模块只负责「怎么分派」，具体规则实现仍在 engine / haunt_rules，
  避免把引擎逻辑复制到这里造成第二份维护。

兼容门面（2026-10-06 拆分轮）
------------------------------
实现按剧本拆在同目录 ``haunts/`` 包（base.py + 每本一个 haunt_XX_<mode>.py，
注册沿 GenericModeHandler 子类树自动完成）。本模块把原 haunt_modes 的一切
公开名字原样再导出——`from haunt_modes import X`、`from .haunt_modes import X`、
`import haunt_modes as hm` 与后端别名壳的模块同一性（check_core_drift）
都不受影响；类体逐字未动，拆分等价性由注册表比对 + 黄金回放 186 条护栏证明。
"""
from __future__ import annotations

try:  # 包上下文：python -m game / 后端别名壳 / from .haunt_modes import ...
    from .haunts import *  # noqa: F401,F403
    from .haunts import (  # noqa: F401
        _MODE_HANDLERS,
        _is_last_in_round,
        _monster_id,
        get_mode_handler,
        register_mode,
        registered_modes,
    )
except ImportError:  # pragma: no cover - 直接脚本执行（sys.path = game/ 本身）
    from haunts import *  # noqa: F401,F403  type: ignore
    from haunts import (  # noqa: F401  type: ignore
        _MODE_HANDLERS,
        _is_last_in_round,
        _monster_id,
        get_mode_handler,
        register_mode,
        registered_modes,
    )
