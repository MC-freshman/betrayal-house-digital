from __future__ import annotations

from ._imports import ActionCommand, GameEngine, Player

class HauntDecisions:
    def _bot_haunt_actions(self, engine: GameEngine, player: Player) -> list:
        """机器人眼里的剧本行动：模式层声明"现在别做"的从列表里拿掉。

        `bot_action_blocked` 原先只挡寻路目标。18 号屏息没有 rooms 字段，
        挡不到，于是它成了"无孢子房间里唯一可点的行动"——机器人每回合
        先屏息，再被 `_pending_haunt_action_here` 判成"下回合还能在这儿做"，
        整个人就钉在原地（seed113/3p 实测屏息 359 次，削弱 0/3）。
        """
        actions = list(engine.available_haunt_actions(player))
        blocked = getattr(engine._mode_handler(), "bot_action_blocked", None)
        if not callable(blocked):
            return actions
        return [
            action
            for action in actions
            if not blocked(engine, player, str(getattr(action, "id", "")))
        ]

    def _pending_haunt_action_here(self, engine: GameEngine, player: Player) -> bool:
        """本房间是否还有一次"这回合已用完、下回合还能做"的剧本行动。

        引擎的可用行动列表会因为"本回合已用过剧本行动"直接返回空，
        所以这里临时清掉标记问一次，看完再还原。
        """
        used = engine._haunt_rule_state().setdefault("actions_used", {})
        key = str(player.id)
        saved = used.get(key)
        used[key] = False
        try:
            return bool(self._bot_haunt_actions(engine, player))
        finally:
            if saved is None:
                used.pop(key, None)
            else:
                used[key] = saved

    def _try_haunt_action(self, engine: GameEngine, player: Player) -> bool:
        actions = self._bot_haunt_actions(engine, player)
        if not actions:
            return False
        if player.bot_difficulty == "easy" and engine.rng.random() < 0.3:
            return False

        def score(action) -> int:
            text = f"{action.id} {action.label}"
            value = 50
            if any(token in text for token in ["银弹", "左轮", "放逐", "制作", "搜索"]):
                value += 35
            if any(token in text for token in ["交给", "交出"]):
                value += 20
            if player.bot_difficulty == "hard":
                value += 15
            priority = getattr(engine._mode_handler(), "bot_action_priority", None)
            if callable(priority):
                value += int(priority(engine, player, action.id) or 0)
            return value

        action = max(actions, key=score)
        return engine.execute_command(
            ActionCommand("haunt_action", player.id, {"action_id": action.id, "data": action.data})
        )

    def _bot_wants_explore(self, engine: GameEngine, player: Player) -> bool:
        """剧本声明"现在必须去翻新房间找牌"（duck-typed `bot_wants_explore`）。

        39 号实测（seed109/4p）：戒指还压在预兆牌堆里，而作祟阶段机器人几乎
        不去探索（探索只在 EXPLORE 阶段有大额加分），继承人在王座前干等到
        400 回合。钩子返回 True 时，探索选项的权重抬到与剧本目标同档之上。
        """
        handler = engine._mode_handler()
        wants = getattr(handler, "bot_wants_explore", None)
        if not callable(wants):
            return False
        return bool(wants(engine, player))

    def _leave_after_action(self, engine: GameEngine, player: Player) -> bool:
        """剧本声明"本回合剧本行动做完后必须挪窝"（duck-typed，默认 False）。

        27 号实测：英雄贴着 Blob 做完知识检定后，`_pending_haunt_action_here`
        判定"下回合还能在这儿做"，于是原地过夜——下一个怪物回合 Blob 正好
        扩张进这间房，人直接被同化（seed101/3p 两名英雄都没活过两个回合）。
        真人贴边看一眼就会退开，这里把"要不要原地等"交给剧本决定。
        """
        handler = engine._mode_handler()
        leave = getattr(handler, "bot_leave_after_action", None)
        return bool(leave(engine, player)) if callable(leave) else False
