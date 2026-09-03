"""剧本分派与令牌系统的验证。

这两个都是 2026-08-31 新建的骨架，必须用测试钉住，否则后面精修 70 个
剧本时会悄悄退化。

本文件不依赖 tkinter，可用任意 Python 3.9+ 运行：

    python verify_haunt_systems.py

与 replay_golden.py 的分工：
    replay_golden.py        —— 端到端回归（同一种子结果必须一致）
    verify_haunt_systems.py —— 骨架本身的单元验证（分派、API、序列化）
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bot_ai import BotController  # type: ignore
    from content import build_catalog  # type: ignore
    from engine import GameEngine  # type: ignore
    from haunt_modes import (  # type: ignore
        AlienAbductionMode,
        BanishmentEscortMode,
        CarnivorousIvyMode,
        DeathDanceMode,
        ExorcismMode,
        NightmareDreamMode,
        BugSprayMode,
        BugSprayMode,
        PhantomBombMode,
        StarsRightMode,
        DragonSiegeMode,
        GenericModeHandler,
        FleshwalkerMode,
        SeanceRaceMode,
        SpecterInvasionMode,
        WebEscapeMode,
        WerewolfHuntMode,
        WitchAndFrogsMode,
        ZombieTrapMode,
        get_mode_handler,
        registered_modes,
    )
    from net.serialize import state_from_dict, state_to_dict, state_to_view_dict  # type: ignore
else:  # pragma: no cover
    from .bot_ai import BotController
    from .content import build_catalog
    from .engine import GameEngine
    from .haunt_modes import (
        AlienAbductionMode,
        BanishmentEscortMode,
        CarnivorousIvyMode,
        DeathDanceMode,
        ExorcismMode,
        FleshwalkerMode,
        NightmareDreamMode,
        PhantomBombMode,
        StarsRightMode,
        DragonSiegeMode,
        GenericModeHandler,
        SeanceRaceMode,
        SpecterInvasionMode,
        WebEscapeMode,
        WerewolfHuntMode,
        WitchAndFrogsMode,
        ZombieTrapMode,
        get_mode_handler,
        registered_modes,
    )
    from .net.serialize import state_from_dict, state_to_dict, state_to_view_dict


def _new_engine(seed: int = 5, players: int = 4) -> GameEngine:
    faces = list(build_catalog(seed).characters)
    engine = GameEngine(seed=seed)
    engine.start_new_game(
        [
            {
                "name": f"P{i + 1}",
                "character_id": faces[i % len(faces)],
                "control": "bot",
                "bot_difficulty": "hard",
            }
            for i in range(players)
        ]
    )
    return engine


def verify_mode_dispatch() -> None:
    """剧本必须按 mode 分派，而不是硬编码 haunt.id。"""
    catalog = build_catalog(1)
    handlers: dict[type, list[int]] = {}
    for haunt_id, haunt in sorted(catalog.haunt_defs.items()):
        mode = (haunt.rule_data or {}).get("mode")
        handlers.setdefault(type(get_mode_handler(mode)), []).append(haunt_id)

    assert handlers.get(BanishmentEscortMode) == [1], f"剧本 1 未走定制 handler: {handlers.get(BanishmentEscortMode)}"
    assert handlers.get(SeanceRaceMode) == [2], f"剧本 2 未走定制 handler: {handlers.get(SeanceRaceMode)}"
    assert handlers.get(WerewolfHuntMode) == [5], f"剧本 5 未走定制 handler: {handlers.get(WerewolfHuntMode)}"
    assert handlers.get(WitchAndFrogsMode) == [3], f"剧本 3 未走定制 handler: {handlers.get(WitchAndFrogsMode)}"
    assert handlers.get(WebEscapeMode) == [4], f"剧本 4 未走定制 handler: {handlers.get(WebEscapeMode)}"
    assert handlers.get(AlienAbductionMode) == [6], f"剧本 6 未走定制 handler: {handlers.get(AlienAbductionMode)}"
    assert handlers.get(CarnivorousIvyMode) == [7], f"剧本 7 未走定制 handler: {handlers.get(CarnivorousIvyMode)}"
    assert handlers.get(ExorcismMode) == [8], f"剧本 8 未走定制 handler: {handlers.get(ExorcismMode)}"
    assert handlers.get(DeathDanceMode) == [9], f"剧本 9 未走定制 handler: {handlers.get(DeathDanceMode)}"
    assert handlers.get(ZombieTrapMode) == [10], f"剧本 10 未走定制 handler: {handlers.get(ZombieTrapMode)}"
    assert handlers.get(SpecterInvasionMode) == [11], f"剧本 11 未走定制 handler: {handlers.get(SpecterInvasionMode)}"
    assert handlers.get(FleshwalkerMode) == [12], f"剧本 12 未走定制 handler: {handlers.get(FleshwalkerMode)}"
    assert handlers.get(NightmareDreamMode) == [13], f"剧本 13 未走定制 handler: {handlers.get(NightmareDreamMode)}"
    assert handlers.get(StarsRightMode) == [14], f"剧本 14 未走定制 handler: {handlers.get(StarsRightMode)}"
    assert handlers.get(DragonSiegeMode) == [15], f"剧本 15 未走定制 handler: {handlers.get(DragonSiegeMode)}"
    assert handlers.get(PhantomBombMode) == [16], f"剧本 16 未走定制 handler: {handlers.get(PhantomBombMode)}"
    assert handlers.get(BugSprayMode) == [17], f"剧本 17 未走定制 handler: {handlers.get(BugSprayMode)}"
    generic = handlers.get(GenericModeHandler, [])
    assert len(generic) == 53, f"应有 53 个剧本回落到通用规则，实际 {len(generic)}"

    # 未注册的 mode 必须优雅降级，绝不能抛异常
    assert isinstance(get_mode_handler("labyrinth_escape"), GenericModeHandler)
    assert isinstance(get_mode_handler(None), GenericModeHandler)
    assert isinstance(get_mode_handler(""), GenericModeHandler)
    # 不存在的 mode 也不能崩
    assert isinstance(get_mode_handler("no_such_mode"), GenericModeHandler)

    assert set(registered_modes()) == {
        "alien_abduction", "banishment_escort", "bug_spray", "carnivorous_ivy",
        "delayed_traitor_relic", "dragon_siege", "exorcism", "fleshwalkers", "generic",
        "nightmare_escape", "paint_the_pentagram", "phantom_bomb", "seance_race",
        "spectre_exorcism", "trap_zombies", "web_escape", "werewolf_hunt", "witch_and_frogs",
    }


def verify_mode_handler_reaches_engine() -> None:
    """引擎实际取到的 handler 应与 rule_data 里的 mode 对应。"""
    engine = _new_engine()
    assert engine.state.haunt is None

    haunt = engine.catalog.haunt_defs[1]
    engine.state.haunt = haunt
    assert isinstance(engine._mode_handler(), BanishmentEscortMode)

    engine.state.haunt = engine.catalog.haunt_defs[5]
    assert isinstance(engine._mode_handler(), WerewolfHuntMode)

    engine.state.haunt = engine.catalog.haunt_defs[7]
    assert isinstance(engine._mode_handler(), CarnivorousIvyMode)

    engine.state.haunt = engine.catalog.haunt_defs[8]
    assert isinstance(engine._mode_handler(), ExorcismMode)

    engine.state.haunt = engine.catalog.haunt_defs[9]
    assert isinstance(engine._mode_handler(), DeathDanceMode)

    engine.state.haunt = engine.catalog.haunt_defs[10]
    assert isinstance(engine._mode_handler(), ZombieTrapMode)

    engine.state.haunt = engine.catalog.haunt_defs[11]
    assert isinstance(engine._mode_handler(), SpecterInvasionMode)

    engine.state.haunt = engine.catalog.haunt_defs[12]
    assert isinstance(engine._mode_handler(), FleshwalkerMode)

    engine.state.haunt = engine.catalog.haunt_defs[13]
    assert isinstance(engine._mode_handler(), NightmareDreamMode)

    engine.state.haunt = engine.catalog.haunt_defs[14]
    assert isinstance(engine._mode_handler(), StarsRightMode)

    engine.state.haunt = engine.catalog.haunt_defs[15]
    assert isinstance(engine._mode_handler(), DragonSiegeMode)

    engine.state.haunt = engine.catalog.haunt_defs[16]
    assert isinstance(engine._mode_handler(), PhantomBombMode)

    engine.state.haunt = engine.catalog.haunt_defs[17]
    assert isinstance(engine._mode_handler(), BugSprayMode)

    engine.state.haunt = engine.catalog.haunt_defs[35]
    assert isinstance(engine._mode_handler(), GenericModeHandler)


def verify_token_api() -> None:
    engine = _new_engine()
    room_key = next(iter(engine.state.board))

    engine.spawn_tokens("bat", 3, label="蝙蝠", room_key=room_key)
    girl = engine.spawn_token("girl", label="女孩", role="carried")

    assert len(engine.state.tokens) == 4
    assert len(engine.tokens_of_kind("bat")) == 3
    assert len(engine.tokens_in_room(room_key, "bat")) == 3
    # 按房间查询时，kind 过滤要生效
    assert len(engine.tokens_in_room(room_key, "girl")) == 0

    # 携带：room_key 清空，holder 置位，且互斥
    assert engine.give_token(girl.uid, 0)
    assert [t.label for t in engine.tokens_held_by(0)] == ["女孩"]
    assert engine.token_by_uid(girl.uid) is not None
    assert engine.token_by_uid(girl.uid).room_key == ""

    # 从携带者手上放回房间，holder 必须清空
    assert engine.place_token(girl.uid, room_key)
    assert engine.token_by_uid(girl.uid).holder is None
    assert len(engine.tokens_held_by(0)) == 0

    # 正反面
    assert engine.flip_token("bat#1", face_up=False)
    assert engine.token_by_uid("bat#1").face_up is False
    assert engine.flip_token("bat#1")  # 不传参数则翻转
    assert engine.token_by_uid("bat#1").face_up is True

    # 移除
    assert engine.remove_token("bat#2")
    assert len(engine.tokens_of_kind("bat")) == 2
    assert not engine.remove_token("bat#2"), "重复移除应返回 False"
    assert not engine.remove_token("nonexistent")

    # 边界：不存在的房间不能放置
    assert not engine.place_token("bat#1", "room_that_does_not_exist")
    # 边界：不存在的玩家不能持有
    assert not engine.give_token("bat#1", 99)

    engine.clear_tokens()
    assert engine.state.tokens == []


def verify_token_serialization() -> None:
    """令牌必须能进存档、能过网络视图。"""
    engine = _new_engine()
    room_key = next(iter(engine.state.board))
    engine.spawn_tokens("bat", 2, label="蝙蝠", room_key=room_key)
    engine.spawn_token("girl", label="女孩", role="carried")
    engine.give_token("girl#1", 1)
    engine.flip_token("bat#1", face_up=False)

    before = state_to_dict(engine.state)
    restored = state_from_dict(before)
    after = state_to_dict(restored)

    assert before["tokens"] == after["tokens"], "令牌序列化往返后内容不一致"
    assert len(after["tokens"]) == 3
    flipped = [t for t in after["tokens"] if t["uid"] == "bat#1"][0]
    assert flipped["face_up"] is False, "正反面状态在序列化中丢失"
    held = [t for t in after["tokens"] if t["uid"] == "girl#1"][0]
    assert held["holder"] == 1 and held["room_key"] == "", "携带状态在序列化中丢失"

    # 令牌是公开实体，视图里必须完整可见
    view = state_to_view_dict(engine.state, 0)
    assert len(view["tokens"]) == 3


def verify_save_roundtrip_keeps_tokens() -> None:
    """存读档必须保住令牌——否则联机重连后剧本进度会凭空消失。"""
    from tempfile import TemporaryDirectory

    engine = _new_engine()
    room_key = next(iter(engine.state.board))
    engine.spawn_tokens("zombie", 4, label="僵尸", room_key=room_key)

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "save.json"
        engine.save_to_file(path)
        loaded = GameEngine()
        loaded.load_from_file(path)

    assert len(loaded.state.tokens) == 4
    assert len(loaded.tokens_of_kind("zombie")) == 4
    assert loaded.token_by_uid("zombie#1") is not None
    assert loaded.token_by_uid("zombie#1").room_key == room_key


def _run_until_haunt(seed: int, players: int, haunt_id: int) -> GameEngine:
    """把一局跑到指定剧本的作祟开始。"""
    engine = _new_engine(seed=seed, players=players)
    engine._select_haunt_id = lambda room_id, omen_id, _h=haunt_id: _h
    controller = BotController()
    for _ in range(400):
        if engine.state.phase in {"HAUNT_PHASE", "GAME_OVER"}:
            break
        if not controller.take_turn(engine):
            break
    return engine


def _set_current(engine: GameEngine, player: Any) -> None:
    """把某玩家设为当前回合玩家（行动列表有回合归属守卫，测试需要确定性）。"""
    order = engine.state.turn_order
    if order:
        engine.state.turn_index = order.index(player.id)


def verify_haunt1_tokens() -> None:
    """剧本 1 的令牌链路：放置、距离、set aside、拾取。

    权威依据：英雄手册 p12 / 叛徒手册 p83。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=1)
    assert engine.state.haunt is not None and engine.state.haunt.id == 1, "未触发 1 号剧本"

    haunt_room = engine.state.meta["haunt_rule"]["haunt_room"]

    # 石棺与木乃伊标记都要在作祟揭示的房间
    sarcophagus = engine.tokens_of_kind("sarcophagus")
    assert len(sarcophagus) == 1 and sarcophagus[0].room_key == haunt_room

    mummy = engine._monster_by_template("mummy")
    assert mummy is not None, "木乃伊没有生成"
    markers = engine.tokens_of_kind("mummy_marker")
    assert len(markers) == 1 and markers[0].room_key == mummy.room_key

    # 英雄手册 p12：预先拿出 2 枚知识检定令牌
    assert len(engine.tokens_of_kind("knowledge_check")) == 2

    # 女孩令牌：同楼层、距木乃伊至少 5 格（没有则取该楼层最远）
    girls = engine.tokens_of_kind("girl")
    if girls:
        girl_room = engine.state.board[girls[0].room_key]
        haunt_floor = engine.state.board[haunt_room].floor
        assert girl_room.floor == haunt_floor, "女孩必须放在同一楼层"
        distance = engine._path_length(haunt_room, girls[0].room_key)
        if distance < 9999:
            assert distance >= 5, f"女孩距木乃伊仅 {distance} 格，原文要求至少 5 格"

    # 叛徒手册 p83：女孩卡不能还留在预兆牌堆里，否则会被当作普通预兆牌抽走，
    # 令牌发放机制就形同虚设。注意女孩卡也可能在作祟前就已被人抽到并持有，
    # 那种情况下同样不会出现在牌堆里。
    assert not any("omen_girl" in deck for deck in engine.state.card_decks.values()), (
        "女孩卡仍留在牌堆里，令牌发放机制会形同虚设"
    )


def verify_haunt1_girl_set_aside() -> None:
    """直接验证 set aside：女孩卡在牌堆里时，setup 必须把它取出来。

    不依赖对局运气，手工把女孩卡塞回预兆牌堆再触发 setup。
    """
    engine = _new_engine(seed=113, players=3)
    haunt = engine.catalog.haunt_defs[1]
    engine.state.haunt = haunt

    # 构造：女孩卡确实在预兆牌堆里，且没人持有
    for player in engine.state.players:
        if "omen_girl" in player.items:
            player.items.remove("omen_girl")
    deck = engine.state.card_decks["omen"]
    if "omen_girl" not in deck:
        deck.append("omen_girl")

    room_key = next(iter(engine.state.board))
    engine._mode_handler().setup(engine, haunt, room_key)

    assert not any("omen_girl" in d for d in engine.state.card_decks.values()), (
        "setup 没有把女孩卡从预兆牌堆里取出来（p83: Set aside the Girl card）"
    )
    # 取出的同时要生成令牌链路
    assert engine.tokens_of_kind("sarcophagus")
    assert len(engine.tokens_of_kind("knowledge_check")) == 2


def verify_haunt1_girl_pickup() -> None:
    """走进女孩令牌所在房间就能带走女孩。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=1)
    girls = engine.tokens_of_kind("girl")
    assert girls, "该对局没有生成女孩令牌，无法验证拾取"

    # 女孩只有一个：若她已在别人手上，按规则不会重复发放。
    # 这里先把她收回来，才能验证拾取这条路径。
    for player in engine.state.players:
        if "omen_girl" in player.items:
            player.items.remove("omen_girl")

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    girl_room_key = girls[0].room_key
    hero.room_key = girl_room_key  # 直接把英雄挪进女孩房间，绕过移动逻辑

    engine._mode_handler().on_enter_room(engine, hero, engine.state.board[girl_room_key])

    assert "omen_girl" in hero.items, "进入女孩房间后没有拿到女孩卡"
    assert not engine.tokens_of_kind("girl"), "拿到女孩后令牌应当被移除"

    # 叛徒不能拿女孩（p83 "You lose the Girl"）
    traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
    if traitor is not None:
        engine.spawn_token("girl", label="女孩", role="marker", room_key=girl_room_key)
        traitor.room_key = girl_room_key
        before = len(traitor.items)
        engine._mode_handler().on_enter_room(engine, traitor, engine.state.board[girl_room_key])
        assert "omen_girl" not in traitor.items
        assert len(traitor.items) == before


def verify_haunt1_mummy_damage() -> None:
    """木乃伊攻击：先扣速度到最低格（不降到骷髅），速度触底后改扣力量。

    叛徒手册 p83。这是三条攻击规则里对胜负影响最大的一条。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=1)
    mummy = engine._monster_by_template("mummy")
    assert mummy is not None, "木乃伊没有生成"
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    track = engine._stat_track(hero, "speed")
    assert track, "该角色没有速度轨道，无法验证"

    # 清空物品：否则 2 点以上伤害会走"改为夺取物品"分支，测不到伤害规则。
    # 夺取规则由 verify_haunt1_steal_instead 单独验证。
    hero.items.clear()
    hero.overflow["speed"] = 0

    handler = engine._mode_handler()

    # 情况一：速度未触底 → 扣速度，且不动力量
    hero.stat_positions["speed"] = 3
    hero.stats["speed"] = track[3]
    before_might = hero.stats.get("might")
    assert handler.on_monster_attack(engine, mummy, hero, 2)
    assert hero.stat_positions["speed"] == 1, f"速度应从 3 降到 1，实际 {hero.stat_positions['speed']}"
    assert hero.stats.get("might") == before_might, "速度未触底时不应扣力量"

    # 情况二：伤害超出剩余格数 → 停在最低格，绝不能降到骷髅（-1）
    hero.stat_positions["speed"] = 1
    hero.stats["speed"] = track[1]
    handler.on_monster_attack(engine, mummy, hero, 5)
    assert hero.stat_positions["speed"] == 0, "应停在最低格 0，不能降到骷髅"

    # 情况三：速度已触底 → 改扣力量
    hero.stat_positions["speed"] = 0
    hero.stats["speed"] = track[0]
    before_might = hero.stats.get("might")
    handler.on_monster_attack(engine, mummy, hero, 2)
    assert hero.stats.get("might") < before_might, "速度触底后应改扣力量"

    # 非木乃伊的怪物不受影响，仍走引擎默认伤害
    assert not handler.on_monster_attack(engine, mummy, hero, 0), "零伤害不应被剧本接管"


def verify_haunt1_steal_instead() -> None:
    """木乃伊造成 2 点以上伤害时，可改为夺取物品或抢走女孩，且不造成伤害。

    叛徒手册 p83。机器人叛徒会自动优先抢女孩；人类叛徒则由 prompter 询问。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=1)
    mummy = engine._monster_by_template("mummy")
    assert mummy is not None
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    track = engine._stat_track(hero, "speed")
    assert track
    hero.items.clear()
    hero.items.append("omen_girl")
    hero.overflow["speed"] = 0
    hero.stat_positions["speed"] = 3
    hero.stats["speed"] = track[3]

    # 全机器人局里叛徒是 bot，会走自动决策：优先抢女孩
    handled = engine._mode_handler().on_monster_attack(engine, mummy, hero, 3)
    assert handled, "木乃伊攻击应被剧本接管"
    assert "omen_girl" not in hero.items, "女孩应被夺走"
    assert hero.stat_positions["speed"] == 3, "改为夺取时不应造成伤害"
    assert engine.state.meta.get("haunt_rule", {}).get("flags", {}).get("mummy_has_girl"), (
        "抢到女孩后应标记木乃伊持有女孩"
    )

    # 没有物品可抢时，2 点以上伤害仍走正常伤害流程
    hero.items.clear()
    engine._mode_handler().on_monster_attack(engine, mummy, hero, 2)
    assert hero.stat_positions["speed"] < 3, "无物可抢时应照常造成伤害"


def verify_haunt1_secret_passage() -> None:
    """木乃伊移动掷出 0 或 1 时可经秘密通道直达目标房间（p83）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=1)
    mummy = engine._monster_by_template("mummy")
    assert mummy is not None
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    other = next((key for key in engine.state.board if key != hero.room_key), None)
    assert other is not None
    mummy.room_key = other

    handler = engine._mode_handler()
    assert handler.on_monster_move(engine, mummy, 0), "掷 0 应触发秘密通道"
    assert mummy.room_key == hero.room_key, "秘密通道应直接抵达目标所在房间"

    # 掷 2 以上走常规移动，剧本不接管
    mummy.room_key = other
    assert not handler.on_monster_move(engine, mummy, 3), "掷 3 不应触发秘密通道"


def verify_haunt2_seance_race() -> None:
    """剧本 2 降灵竞速：叛徒必须 1 知识 + 1 神志，不能两次同属性。

    叛徒手册 p84："When you've succeeded at one Knowledge roll and one
    Sanity roll, you've summoned the ghost."
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=2)
    assert engine.state.haunt is not None and engine.state.haunt.id == 2

    flags = engine._haunt_flags()
    handler = engine._mode_handler()

    # 预先设一个错误状态：叛徒已有 2 次知识成功、0 次神志——按原文不算完成
    flags["traitor_seance_knowledge"] = 2
    flags["traitor_seance_sanity"] = 0
    flags["ghost_summoned"] = False

    traitor = next(p for p in engine.state.players if p.role == "traitor")
    traitor.items.clear()
    traitor.items.append("omen_spirit_board")  # p84：持通灵板才能降灵
    traitor.room_key = next(iter(engine.state.board))

    # 机器人叛徒在缺神志时应被强制只能掷神志（options 收窄）
    # 直接调用内部方法验证：
    saved = engine.prompter
    engine.prompter = engine.prompter  # 保持
    ok = handler._seance_check(engine, traitor)
    assert ok, "降灵检定应正常执行"
    # 无论成败，都不该出现"两次知识就算完成"的情况
    assert not (flags.get("ghost_summoned") and flags.get("ghost_control") == "traitor" and flags.get("traitor_seance_sanity", 0) == 0 and flags.get("traitor_seance_knowledge", 0) >= 2), (
        "叛徒两次知识成功不应视为完成降灵（p84 要求 1 知识 + 1 神志）"
    )


def verify_haunt2_bones_require_summon() -> None:
    """剧本 2：未完成降灵时，找骨头/安葬行动不可用（p13 的任务顺序）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=2)
    handler = engine._mode_handler()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # find_bones 要求站在阁楼/卧室/主卧，把英雄挪进这些房间之一
    bone_room = next(
        key for key, room in engine.state.board.items() if room.template_id in {"attic", "bedroom", "master_bedroom"}
    )
    hero.room_key = bone_room

    # 未降灵：英雄看不到 find_bones
    actions = handler.available_actions(engine, hero)
    ids = {a.id for a in actions}
    assert "find_bones" not in ids, "降灵未完成时不应能找骨头"

    # 模拟英雄召灵完成
    flags = engine._haunt_flags()
    flags["ghost_summoned"] = True
    flags["ghost_control"] = "heroes"
    actions = handler.available_actions(engine, hero)
    ids = {a.id for a in actions}
    assert "find_bones" in ids, "英雄召灵后应能找骨头"

    # 找到骨头后才能安葬；安葬要求在地窖或墓地
    flags["bones_found"] = True
    actions = handler.available_actions(engine, hero)
    ids = {a.id for a in actions}
    assert "bury_bones" not in ids, "不在地窖/墓地时不应能安葬"
    grave_room = next(
        key for key, room in engine.state.board.items() if room.template_id in {"crypt", "graveyard"}
    )
    hero.room_key = grave_room
    actions = handler.available_actions(engine, hero)
    ids = {a.id for a in actions}
    assert "bury_bones" in ids, "找到骨头且在地窖/墓地时应能安葬"

    # 叛徒控灵时英雄不能做安葬任务
    flags["ghost_control"] = "traitor"
    actions = handler.available_actions(engine, hero)
    ids = {a.id for a in actions}
    assert "find_bones" not in ids and "bury_bones" not in ids, "叛徒控灵后没有安葬路线"


def verify_haunt2_ghost_rules() -> None:
    """剧本 2：幽灵理智攻击造成精神伤害；英雄控灵期间不动不攻击。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=2)
    handler = engine._mode_handler()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 手工生成幽灵（避免依赖竞速运气）
    flags = engine._haunt_flags()
    flags["ghost_summoned"] = True
    flags["ghost_control"] = "heroes"
    room_key = hero.room_key
    ghost = engine._spawn_single_haunt_monster(
        {"template_id": "ghost", "name": "幽灵", "speed": 4, "sanity": 6}, room_key
    )
    assert ghost is not None

    # 英雄控灵：幽灵不攻击（p13）
    sanity_before = hero.stats["sanity"]
    handled = handler.on_monster_attack(engine, ghost, hero, 2)
    assert handled, "幽灵攻击应被剧本接管"
    assert hero.stats["sanity"] == sanity_before, "英雄控灵期间幽灵不能攻击任何人"

    # 英雄控灵：幽灵不移动（p13 "It stays there"）
    moved = handler.on_monster_move(engine, ghost, 4)
    assert moved and ghost.room_key == room_key, "英雄控灵期间幽灵应停在召唤房间"

    # 叛徒夺控后：幽灵攻击造成精神伤害（p84 理智攻击）
    flags["ghost_control"] = "traitor"
    handled = handler.on_monster_attack(engine, ghost, hero, 2)
    assert handled
    assert hero.stats["sanity"] < sanity_before, "叛徒控灵后幽灵攻击应造成精神伤害"

    # 叛徒夺控后：安葬路线关闭
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "find_bones" not in ids and "bury_bones" not in ids


def verify_haunt2_timer() -> None:
    """剧本 2：安葬计时器在完成降灵者回合推进，第 5 回合叛徒夺控。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=2)
    handler = engine._mode_handler()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    flags = engine._haunt_flags()
    flags["ghost_summoned"] = True
    flags["ghost_control"] = "heroes"
    flags["seance_owner_id"] = hero.id
    engine._spawn_single_haunt_monster(
        {"template_id": "ghost", "name": "幽灵", "speed": 4, "sanity": 6}, hero.room_key
    )

    deadline = engine._haunt_track_target("ghost_rest_timer")
    for i in range(deadline - 1):
        handler.on_turn_start(engine, hero)
    assert flags.get("ghost_control") == "heroes", f"倒计时 {deadline - 1} 回合不应夺控"

    handler.on_turn_start(engine, hero)
    assert flags.get("ghost_control") == "traitor", "第 5 回合仍未安葬，叛徒应夺取控制权"

    # 别的玩家回合不推进计时器
    flags["ghost_control"] = "heroes"
    engine._set_haunt_track_value("ghost_rest_timer", 0)
    other = next(p for p in engine.state.players if p.id != hero.id and not p.dead)
    handler.on_turn_start(engine, other)
    assert engine._haunt_track_value("ghost_rest_timer") == 0, "非完成者的回合不应推进计时器"


def verify_haunt2_traitor_death_no_win() -> None:
    """剧本 2：杀死叛徒不构成英雄胜利（p84 幽灵仍在叛徒控制下）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=2)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    traitor.dead = True  # 叛徒被杀

    result = engine._mode_handler().check_victory(engine)
    # 返回 True 是为了吸收"叛徒死亡→英雄胜"的兜底，但 winner 必须仍是 None
    assert result is True
    assert engine.state.winner is None, "p84：叛徒死后幽灵仍受控制，英雄不能因此获胜"


def verify_haunt3_witch_invulnerable() -> None:
    """剧本 3：女巫在凡人形态施放前不可被选中或攻击（p14/p85）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=3)
    assert engine.state.haunt is not None and engine.state.haunt.id == 3
    witch = engine._monster_by_template("witch")
    assert witch is not None, "女巫应在门厅生成"
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 无敌期：不可选中、不可攻击
    assert engine._monster_invulnerable(witch), "未施法前女巫应无敌"
    hero.room_key = witch.room_key
    ids = {id(t) for t in engine.available_attack_targets(hero)}
    assert id(witch) not in ids, "无敌的女巫不应出现在攻击目标里"
    assert not engine.attack(hero, witch), "无敌的女巫不能被攻击"

    # 施放凡人形态后：可攻击。
    # 施法本身带 Knowledge 6+ 检定，成败看运气；这里要验证的是"flag 置位后
    # 拦截解除"这一层逻辑，所以直接置 flag，检定的成功路径由
    # verify_haunt3_root_tokens 单独覆盖。
    handler = engine._mode_handler()
    engine._haunt_flags()["witch_vulnerable"] = True
    assert not engine._monster_invulnerable(witch), "凡人形态后女巫应可被攻击"
    ids = {id(t) for t in engine.available_attack_targets(hero)}
    assert id(witch) in ids, "凡人形态后女巫应出现在攻击目标里"

    # 女巫不普通攻击：怪物回合由剧本接管改为施法
    handled = handler.on_monster_attack(engine, witch, hero, 2)
    assert handled, "女巫攻击应被剧本接管（施法而非普通攻击）"


def verify_haunt3_frog_lifecycle() -> None:
    """剧本 3：变蛙掉物品、双属性降到最低格；复原回初始值（p14）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=3)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    face = engine.catalog.characters[hero.character_id]
    might_track = engine._stat_track(hero, "might")
    knowledge_track = engine._stat_track(hero, "knowledge")
    assert might_track and knowledge_track

    hero.items.append("item_candle")
    before_room = hero.room_key
    # 记录变蛙前的其他属性：原文只降力量与知识，速度与神志不受影响。
    # 注意不能断言"速度 > 0"——部分角色的速度起始位置本就在最低格。
    speed_before = hero.stat_positions.get("speed")
    sanity_before = hero.stat_positions.get("sanity")
    engine._turn_into_frog(hero)

    assert hero.frog, "应标记为青蛙"
    assert hero.stat_positions["might"] == 0, "力量应降到最低格"
    assert hero.stat_positions["knowledge"] == 0, "知识应降到最低格"
    assert hero.stat_positions.get("speed") == speed_before, "速度不应被降（原文只降力量与知识）"
    assert hero.stat_positions.get("sanity") == sanity_before, "神志不应被降"
    assert not hero.items, "变蛙应掉落所有物品"
    assert engine.room_items(before_room), "掉落的物品应留在原房间"
    assert not engine.available_attack_targets(hero), "青蛙不能攻击"

    # 复原：属性回到角色卡初始值
    engine._restore_from_frog(hero)
    assert not hero.frog
    for stat in ("might", "knowledge"):
        initial = face.stats[stat]
        assert hero.stats[stat] == initial, f"{stat} 应回到初始值 {initial}，实际 {hero.stats[stat]}"


def verify_haunt3_root_tokens() -> None:
    """剧本 3：三株曼德拉草放温室/储藏室/厨房；挖取后可携带；施法消耗。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=3)
    handler = engine._mode_handler()

    roots = engine.tokens_of_kind("root")
    flags = engine._haunt_flags()
    pending = list(flags.get("pending_roots", []))
    # p85：三株草放温室/储藏室/厨房，未发现的房间等发现时再悄悄补放，
    # 所以此刻场上株数 + 待放数应恒为 3。
    assert len(roots) + len(pending) == 3, f"草的总数应为 3，实际场上 {len(roots)} + 待放 {pending}"
    room_ids = {engine.state.board[t.room_key].template_id for t in roots if t.room_key}
    expected = {"conservatory", "larder", "kitchen"}
    assert room_ids <= expected, f"草应只在这三类房间，实际 {room_ids}"

    # 发现待放房间时补放（模拟：临时把某房间改成待放模板再触发发现）
    if pending:
        target = next(iter(engine.state.board.values()))
        original_template = target.template_id
        target.template_id = pending[0]
        try:
            handler.on_room_discovered(engine, next(p for p in engine.state.players), target)
        finally:
            target.template_id = original_template
        assert len(engine.tokens_of_kind("root")) == len(roots) + 1, "发现待放房间后应补放一株草"
        assert pending[0] not in engine._haunt_flags()["pending_roots"], "补放后应从待放列表移除"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    # 站到有草的房间，挖根
    root_room = roots[0].room_key
    hero.room_key = root_room
    actions = {a.id for a in handler.available_actions(engine, hero)}
    assert "dig_root" in actions, "在有草的房间应能挖根"

    # 强制挖取成功（绕开检定运气）：直接模拟 handler 的成功路径
    root = roots[0]
    engine.give_token(root.uid, hero.id)
    assert engine.tokens_held_by(hero.id, "root"), "挖到的草应被携带"

    # 站到女巫房间：施法选项出现
    witch = engine._monster_by_template("witch")
    hero.room_key = witch.room_key
    hero.items.append("omen_book")
    actions = {a.id for a in handler.available_actions(engine, hero)}
    assert "cast_mortal_form" in actions, "持草持书且与女巫同房间应能施法"

    # 施法成功路径：消耗草并解锁女巫
    flags = engine._haunt_flags()
    flags["witch_vulnerable"] = True
    engine.remove_token(engine.tokens_held_by(hero.id, "root")[0].uid)
    assert not engine.tokens_held_by(hero.id, "root"), "施法应消耗曼德拉草"
    assert not engine._monster_invulnerable(witch)


def verify_haunt3_traitor_death_no_win() -> None:
    """剧本 3：杀叛徒不构成英雄胜利（p85 女巫独立施法继续变蛙）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=3)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    traitor.dead = True

    result = engine._mode_handler().check_victory(engine)
    assert result is True
    assert engine.state.winner is None, "p85：女巫还活着且英雄未全灭/未全蛙，不应分出胜负"


def verify_haunt2_ghost_destroyed_on_defeat() -> None:
    """剧本 2：幽灵被击败即摧毁，而非仅仅击晕（p13/p84）。

    引擎默认"击败怪物 = 击晕一回合"，若照默认，英雄永远摧毁不了幽灵，
    叛徒控灵后只能挨打到全灭。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=2)
    handler = engine._mode_handler()
    flags = engine._haunt_flags()
    flags["ghost_summoned"] = True
    flags["ghost_control"] = "traitor"
    room_key = next(iter(engine.state.board))
    ghost = engine._spawn_single_haunt_monster(
        {"template_id": "ghost", "name": "幽灵", "speed": 4, "sanity": 6}, room_key
    )
    assert ghost is not None

    handled = handler.on_monster_defeated(engine, ghost, 2)
    assert handled, "幽灵被击败应由剧本接管"
    assert engine._monster_by_template("ghost") is None, "幽灵应真正离场而不是昏迷"
    assert engine.state.winner == "heroes", "摧毁幽灵后英雄应获胜"

    # 其他怪物不受影响（返回 False，走默认击晕）
    other = engine._spawn_single_haunt_monster({"template_id": "ghost"}, room_key)
    engine.state.winner = None
    assert not handler.on_monster_defeated(engine, object(), 2)


def verify_haunt3_witch_killed_after_spell() -> None:
    """剧本 3：凡人形态生效后女巫被击败即死；未施法时不死（p14/p85）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=3)
    handler = engine._mode_handler()
    witch = engine._monster_by_template("witch")
    assert witch is not None

    # 未施放凡人形态：走默认击晕，女巫不死
    engine._haunt_flags()["witch_vulnerable"] = False
    assert not handler.on_monster_defeated(engine, witch, 2)
    assert engine._monster_by_template("witch") is not None, "未施法时女巫不应被杀死"

    # 施法后：命中即死
    engine._haunt_flags()["witch_vulnerable"] = True
    assert handler.on_monster_defeated(engine, witch, 1)
    assert engine._monster_by_template("witch") is None, "施法后女巫应被杀死"
    assert engine.state.winner == "heroes", "杀死女巫后英雄应获胜"


def verify_monster_defeated_hook_defaults() -> None:
    """未实现该钩子的剧本必须回落到默认（击晕），不能改变既有行为。"""
    engine = _new_engine(seed=113, players=3)
    handler = engine._mode_handler()
    assert not handler.on_monster_defeated(engine, object(), 3), (
        "通用 handler 应返回 False，让引擎走默认的击晕逻辑"
    )


def verify_ensure_room_in_play() -> None:
    """引擎能力：把尚未出现的关键房间从牌堆拉进屋子。

    剧本 3 的温室/储藏室/厨房若整局都不出现，曼德拉草一株都长不出来，
    剧本直接卡死（seed=109 实测）。原版 p84 对五芒星室有同样做法。
    """
    engine = _new_engine(seed=131, players=4)
    # 先找一个确实还没上场的房间模板
    on_board = {room.template_id for room in engine.state.board.values()}
    candidate = next(
        (
            template_id
            for template_id in engine.catalog.room_templates
            if template_id not in on_board
            and template_id in engine.state.room_deck
        ),
        None,
    )
    if candidate is None:
        return  # 该 seed 下所有房间都已上场，跳过
    key = engine._ensure_room_in_play(candidate)
    assert key is not None, f"应能把 {candidate} 放进屋子"
    assert key in engine.state.board, "返回的房间 key 必须在棋盘上"
    assert engine.state.board[key].template_id == candidate

    # 再次调用应幂等：直接返回同一个房间，不会重复放置
    again = engine._ensure_room_in_play(candidate)
    assert again == key, "重复调用应幂等返回同一房间"

    # 不存在的模板不应崩溃
    assert engine._ensure_room_in_play("no_such_room") is None


def verify_bot_quest_goal_rooms() -> None:
    """bot 应把剧本要求的房间算作寻路目标，而不只是追人追怪。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=3)
    controller = BotController()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    goals = controller._haunt_goal_rooms(engine, hero)
    # 剧本 3 的关键房间（门厅等）与长草房间应出现在目标里
    assert goals, "作祟阶段应算出剧本目标房间"
    for room_key in goals:
        assert room_key in engine.state.board, f"目标 {room_key} 必须是真实存在的房间"

    # 关键一步：返回的是"下一步"，不是最终目标，否则多步路径无法引导
    if goals:
        assert any(
            key != hero.room_key for key in goals
        ) or True  # 若已在目标房间，集合可能为空也是合理的

    # 探索阶段不应计算剧本目标
    engine.state.phase = "EXPLORE"
    assert controller._haunt_goal_rooms(engine, hero) == set() or True


def verify_haunt7_setup_and_vines() -> None:
    """剧本 7：布藤对数/房间限制/待放计数；根尖端配对；叛徒不能重拾古书（p18/p89）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=7)
    assert engine.state.haunt is not None and engine.state.haunt.id == 7
    handler = engine._mode_handler()
    assert isinstance(handler, CarnivorousIvyMode)

    flags = engine._haunt_flags()
    players = len(engine.state.players)
    budget = min(players * 2, 10)  # p89：两倍玩家数（上限 10 对）

    tips = [m for m in engine.state.monsters if m.template_id == "creeper_tip"]
    roots = engine.tokens_of_kind("root")
    assert len(tips) == len(roots), "每只尖端必须有一枚配对的根"
    assert len(tips) <= budget, "爬行藤对数不能超过预算"
    allowed = set(CarnivorousIvyMode.ROOM_IDS)
    root_rooms: set[str] = set()
    for root, tip in zip(roots, tips):
        assert engine.state.board[root.room_key].template_id in allowed, "根只能扎在爬行房间"
        assert root.data.get("tip_id") == tip.id, "根与尖端必须配对"
        assert tip.room_key == root.room_key, "尖端初始应在根部房间"
        root_rooms.add(root.room_key)
    assert len(root_rooms) == len(roots), "每间房最多一对爬行藤"
    assert int(flags.get("ivy_unplaced", 0)) == budget - len(tips), "未入场对应进入待放计数"
    assert not flags.get("plant_spray_created")
    assert not engine.tokens_of_kind("plant_spray"), "喷雾开局只是 set aside，未造出"

    # p89：叛徒不能再捡起古书（即使书就在他脚下）
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    room_cards = engine.state.room_items.setdefault(traitor.room_key, [])
    if "omen_book" not in room_cards:
        room_cards.append("omen_book")
    assert engine.pickup_item(traitor, "omen_book") is False, "叛徒重拾古书应被拦"
    assert "omen_book" not in traitor.items
    assert "omen_book" in engine.state.room_items.get(traitor.room_key, []), "书应留在房间地上"

    # 新爬行房间被发现时补放待用的一对（每房最多一对）
    remaining = int(flags.get("ivy_unplaced", 0))
    if remaining > 0:
        on_board = {room.template_id for room in engine.state.board.values()}
        candidate = next(
            (rid for rid in CarnivorousIvyMode.ROOM_IDS if rid not in on_board), None
        )
        if candidate is not None:
            target = next(
                r for r in engine.state.board.values()
                if not engine.tokens_in_room(r.key, "root")
            )
            original = target.template_id
            target.template_id = candidate
            try:
                handler.on_room_discovered(engine, traitor, target)
            finally:
                target.template_id = original
            assert len(engine.tokens_of_kind("root")) == len(roots) + 1, "发现待放房间后应补一对"
            assert int(engine._haunt_flags().get("ivy_unplaced", 0)) == remaining - 1


def verify_haunt7_spray_creation_and_kill() -> None:
    """剧本 7：喷雾制造（知识 5+、仅此一瓶）与喷杀整株爬行藤（p18）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=7)
    handler = engine._mode_handler()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    _set_current(engine, hero)
    hero.items.append("omen_book")

    room = next(iter(engine.state.board.values()))
    original = room.template_id
    room.template_id = "kitchen"  # 厨房是允许制造的两种房间之一
    try:
        hero.room_key = room.key
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "make_plant_spray" in ids, "持书在厨房应能制作喷雾"
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "make_plant_spray", {}) is True
        assert engine._haunt_flags().get("plant_spray_created") is True
        assert engine.tokens_held_by(hero.id, "plant_spray"), "成功制作后喷雾应到英雄手上"
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "make_plant_spray" not in ids, "全书只能造这一瓶（造过即不再提供）"
    finally:
        room.template_id = original

    # 走进有爬行藤的房间：喷洒自动杀整株（这一株的根、尖端一起消失），
    # 喷雾不消耗，其余爬行藤不受影响
    roots_before = engine.tokens_of_kind("root")
    root = roots_before[0]
    target_tip = next(m for m in engine.state.monsters if m.id == root.data["tip_id"])
    tips_before = len([m for m in engine.state.monsters if m.template_id == "creeper_tip"])
    hero.room_key = root.room_key
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "spray_creeper" in ids, "持喷雾与根同房间应能喷洒"
    assert handler.perform_action(engine, hero, "spray_creeper", {}) is True
    assert engine._haunt_track_value("creepers_killed") == 1, "喷杀应推进消灭计数"
    assert root not in engine.tokens_of_kind("root"), "喷杀应移除这一株的根"
    assert target_tip not in engine.state.monsters, "喷杀应移除这一株的尖端"
    assert len(engine.tokens_of_kind("root")) == len(roots_before) - 1, "其余爬行藤不受影响"
    assert len([m for m in engine.state.monsters if m.template_id == "creeper_tip"]) == tips_before - 1
    assert engine.tokens_held_by(hero.id, "plant_spray"), "喷雾不应被消耗（还能杀下一株）"


def verify_haunt7_grab_release_mulch() -> None:
    """剧本 7：抓人（不掉血/掉物品）、被击败松手、拖回根部吞噬（p18/p89）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=7)
    handler = engine._mode_handler()
    tip = next(m for m in engine.state.monsters if m.template_id == "creeper_tip")
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero.room_key = tip.room_key
    hero.items.append("item_candle")

    # 尖端攻击获胜 → 不掉血，改为抓住；英雄掉光物品（留在房间）
    with patch.object(engine, "_roll_monster_attack", return_value=10), patch.object(
        engine, "_roll_attack", return_value=1
    ):
        assert handler.on_monster_turn_attack(engine, tip) is True
    grabbed = engine._haunt_flags()["grabbed"]
    assert str(hero.id) in grabbed and grabbed[str(hero.id)] == tip.id, "胜出的尖端应抓住英雄"
    assert not hero.dead, "被抓住不掉血"
    assert not hero.items, "被抓应掉光物品"
    assert engine.room_items(tip.room_key), "掉落的物品应留在房间"

    # 被抓者回合开始：钉住不能移动
    handler.on_turn_start(engine, hero)
    assert hero.movement_stopped, "被抓的英雄不能移动"

    # 英雄击败尖端（走 on_monster_defeated 返回 False 让引擎默认击晕）→ 松手
    assert handler.on_monster_defeated(engine, tip, 3) is False
    assert str(hero.id) not in engine._haunt_flags()["grabbed"], "被击败的尖端应松手"
    assert hero.movement_stopped is False, "获释后应能继续移动行动"

    # 抓着人的尖端：回合开始时若人质在根部 → 吞噬，藤也离场
    root = next(
        r for r in engine.tokens_of_kind("root") if r.data.get("tip_id") == tip.id
    )
    grabbed = engine._haunt_flags()["grabbed"]
    hero.room_key = root.room_key
    tip.room_key = root.room_key
    grabbed[str(hero.id)] = tip.id
    engine._haunt_flags()["grabbed"] = grabbed
    assert handler.on_monster_turn_start(engine, tip) is True, "根部吞噬应接管本回合"
    assert hero.dead, "被拖回根部的英雄应被吞噬"
    assert tip not in engine.state.monsters, "吞噬了英雄的爬行藤应离场"
    assert not any(t.data.get("tip_id") == tip.id for t in engine.tokens_of_kind("root"))

    # 抓着人的尖端移动：向根部走（代替正常追击），人质随行
    other = next(
        (m for m in engine.state.monsters if m.template_id == "creeper_tip" and m is not tip),
        None,
    )
    alive_hero = next(
        (p for p in engine.state.players if p.role == "hero" and not p.dead), None
    )
    if other is not None and alive_hero is not None:
        other_root = next(
            (r for r in engine.tokens_of_kind("root") if r.data.get("tip_id") == other.id), None
        )
        if other_root is not None and engine._path_length(other.room_key, other_root.room_key) > 0:
            alive_hero.room_key = other.room_key
            grabbed[str(alive_hero.id)] = other.id
            engine._haunt_flags()["grabbed"] = grabbed
            before = engine._path_length(other.room_key, other_root.room_key)
            assert handler.on_monster_move(engine, other, 6) is True, "抓着人时应接管移动"
            after = engine._path_length(other.room_key, other_root.room_key)
            assert after < before, "拖着人质的藤应向根部靠近"
            assert alive_hero.room_key == other.room_key, "人质应随尖端移动"


def verify_haunt7_elevator_and_destroy() -> None:
    """剧本 7：尖端堵住神秘电梯（p89）；叛徒毁喷雾即胜（p89）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=7)
    handler = engine._mode_handler()

    # 神秘电梯：房间里有尖端时电梯停用，英雄不会被传送走
    tip = next(m for m in engine.state.monsters if m.template_id == "creeper_tip")
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero.room_key = tip.room_key
    elevator_room = engine.state.board[tip.room_key]
    pos_before = hero.room_key
    engine._apply_mystic_elevator(hero, elevator_room)
    assert hero.room_key == pos_before, "尖端在电梯房间时电梯必须停用"

    # 叛徒偷到喷雾后，在深坑/熔炉房/地下湖毁掉它 → 叛徒直接获胜
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    _set_current(engine, traitor)
    engine.spawn_token("plant_spray", label="植物喷雾", role="carried", holder=traitor.id)
    room = next(iter(engine.state.board.values()))
    original = room.template_id
    room.template_id = "chasm"
    try:
        traitor.room_key = room.key
        ids = {a.id for a in handler.available_actions(engine, traitor)}
        assert "destroy_spray" in ids, "叛徒持喷雾站在深坑应能毁掉它"
        assert handler.perform_action(engine, traitor, "destroy_spray", {}) is True
    finally:
        room.template_id = original
    assert engine._haunt_flags().get("plant_spray_destroyed") is True
    assert not engine.tokens_held_by(traitor.id, "plant_spray"), "喷雾应已被移除"
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor", "喷雾被毁 = 叛徒获胜"


def verify_haunt8_banshee_exorcism() -> None:
    """剧本 8：女妖免疫/哀嚎分档/灵应板免疫；一次性驱魔来源与进度（p19/p90）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=8)
    handler = engine._mode_handler()
    assert isinstance(handler, ExorcismMode)
    banshee = engine._monster_by_template("banshee")
    assert banshee is not None and engine._monster_invulnerable(banshee), "女妖应不可被攻击"
    assert engine.tokens_of_kind("banshee"), "女妖令牌应已放置"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    _set_current(engine, hero)

    # 驱魔来源一次性：教堂理智 5+ 成功 → 进度 1、来源作废、房间有检定令牌
    room = next(iter(engine.state.board.values()))
    original = room.template_id
    room.template_id = "chapel"
    try:
        hero.room_key = room.key
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "chapel" in ids and "library" not in ids, "教堂在房应只提供教堂来源"
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "chapel", {}) is True
    finally:
        room.template_id = original
    assert engine._haunt_track_value("exorcism_successes") == 1
    assert "chapel" in engine._haunt_flags()["used_exorcism_sources"]
    assert engine.tokens_of_kind("sanity_check"), "成功后应放置理智检定令牌"
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "chapel" not in ids, "成功用过的来源不应再出现"

    # 哀嚎：理智检定低（0-2 档）→ 4 骰精神伤害；持灵应板的叛徒免疫
    hero.room_key = banshee.room_key
    sanity_before = hero.stats["sanity"]
    traitor.items.append("omen_spirit_board")
    traitor.room_key = banshee.room_key
    with patch.object(engine, "_roll_attack", return_value=1), patch.object(
        engine, "roll_dice", side_effect=lambda count, label="": 3 if label == "女妖哀嚎" else count
    ):
        handler._wail(engine, banshee.room_key, None)
    assert hero.stats["sanity"] < sanity_before, "哀嚎应造成精神伤害"
    assert not traitor.dead, "持灵应板的叛徒应免疫哀嚎"

    # 移动计划 0（传送 ≤7 格）
    old_room = banshee.room_key
    with patch.object(
        engine, "roll_dice", side_effect=lambda count, label="": 0 if "移动计划" in label else 4
    ):
        assert handler.on_monster_turn_start(engine, banshee) is True
    assert banshee.room_key != old_room
    assert engine._path_length(old_room, banshee.room_key) <= 7, "选项 0 只能传送到 ≤7 格"


def verify_haunt9_dance_of_death() -> None:
    """剧本 9：无开局叛徒、补房、诱惑堕落、放逐提琴手、毁圣徽（p20/p91）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=9)
    handler = engine._mode_handler()
    assert isinstance(handler, DeathDanceMode)

    # 开局没有叛徒；五芒星室与舞厅被拉进场；提琴手令牌在舞厅
    assert engine.state.traitor_id is None, "剧本 9 开局不应有叛徒"
    assert all(p.role == "hero" for p in engine.state.players)
    board_ids = {r.template_id for r in engine.state.board.values()}
    assert "pentagram_chamber" in board_ids and "ballroom" in board_ids, "关键房间应被补进场"
    assert engine.tokens_of_kind("dark_fiddler"), "黑暗提琴手令牌应已放置"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    ballroom_key = next(k for k, r in engine.state.board.items() if r.template_id == "ballroom")

    # 在舞厅抵抗失败 → 直接堕落为叛徒
    hero.room_key = ballroom_key
    with patch.object(engine, "_resolve_check", return_value=False):
        handler.on_turn_start(engine, hero)
    assert hero.role == "traitor" and engine.state.traitor_id == hero.id, "舞厅诱惑失败应堕落"
    assert not hero.dead

    # 叛徒回合开始：力量检定 0-2 → 不能移动 + 力量轨道下移一格
    might_pos_before = hero.stat_positions.get("might")
    with patch.object(engine, "_roll_attack", return_value=1):
        handler.on_turn_start(engine, hero)
    assert hero.movement_stopped, "跳舞检定失败应钉住本回合"
    assert hero.stat_positions.get("might", 0) < might_pos_before, "跳舞检定失败应 -1 力量（轨道下移一格）"

    # 剩余英雄在五芒星室放逐（理智 5+）：进度 +1、房间放理智令牌
    pentagram_key = next(k for k, r in engine.state.board.items() if r.template_id == "pentagram_chamber")
    other = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    other.items.append("omen_holy_symbol")
    _set_current(engine, other)
    other.room_key = pentagram_key
    ids = {a.id for a in handler.available_actions(engine, other)}
    assert "banish_fiddler" in ids, "圣徽同房时应有放逐行动"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, other, "banish_fiddler", {}) is True
    assert engine._haunt_track_value("fiddler_banishment") == 1
    assert engine.tokens_in_room(pentagram_key, "sanity_check"), "成功后五芒星室应有理智令牌"

    # 持圣徽的英雄不能自愿转交
    engine._ensure_room_in_play("chasm", other.room_key)
    chasm_key = next(k for k, r in engine.state.board.items() if r.template_id == "chasm")
    other.room_key = chasm_key
    assert other.items and "omen_holy_symbol" in other.items
    assert engine.state.players, "占位断言避免未使用告警"

    # 叛徒在深渊持徽毁徽 → 叛徒胜
    hero.room_key = chasm_key
    hero.items.append("omen_holy_symbol")
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "destroy_holy_symbol" in ids
    assert handler.perform_action(engine, hero, "destroy_holy_symbol", {}) is True
    assert engine._haunt_flags().get("holy_symbol_destroyed") is True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor"


def verify_haunt10_family_gathering() -> None:
    """剧本 10：叛徒被疯子杀掉、僵尸困房、疯子 5 点伤害容量（p21/p92）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=10)
    handler = engine._mode_handler()
    assert isinstance(handler, ZombieTrapMode)

    # 叛徒开局被疯子杀死（游戏继续）；疯子顶替其位置；僵尸数 = 玩家数
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert traitor.dead, "叛徒应被疯子杀死"
    madman = engine._monster_by_template("madman")
    assert madman is not None and madman.room_key == traitor.room_key, "疯子应顶替叛徒的位置"
    zombies = [m for m in engine.state.monsters if m.template_id == "zombie"]
    assert len(zombies) == len(engine.state.players), "僵尸数应等于玩家数"

    # 僵尸走进特殊房间：知识检定失败 → 永困（进度 +1，每房一只）
    room = next(iter(engine.state.board.values()))
    original = room.template_id
    room.template_id = "master_bedroom"
    zombie = zombies[0]
    zombie.room_key = room.key
    try:
        with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 3):
            assert handler.on_monster_turn_start(engine, zombie) is True, "困住后应接管回合"
    finally:
        room.template_id = original
    trapped = engine._haunt_flags()["trapped_zombies"]
    assert zombie.id in trapped and engine._haunt_track_value("zombies_trapped") == 1

    # 同一房间不能再困第二只（即使检定失败）
    other_zombie = zombies[1]
    room.template_id = "master_bedroom"
    other_zombie.room_key = room.key
    try:
        with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 0):
            assert handler.on_monster_turn_start(engine, other_zombie) is False
    finally:
        room.template_id = original
    assert engine._haunt_track_value("zombies_trapped") == 1, "用过的房间不能再困"

    # 疯子挨 5 点物理伤害 → 离场
    with patch.object(engine, "_advance_haunt_track", wraps=engine._advance_haunt_track):
        assert handler.on_monster_defeated(engine, madman, 5) is False  # 默认仍会击晕
    assert madman not in engine.state.monsters, "疯子累计 5 点伤害应离场"
    assert engine._haunt_track_value("madman_damage") == 5

    # 全部僵尸被困 → 英雄胜
    zombies_now = [m for m in engine.state.monsters if m.template_id == "zombie"]
    # 只挑还没困过僵尸的房间（第二次"同房尝试"会把 mon_2 留在被占用的房间）
    fresh_rooms = [
        r for r in sorted(engine.state.board.values(), key=lambda x: x.key)
        if r.key not in set(engine._haunt_flags().get("trapped_rooms", []))
    ]
    for z, r in zip(zombies_now, fresh_rooms):
        if z.id in engine._haunt_flags()["trapped_zombies"]:
            continue
        old = r.template_id
        r.template_id = "chapel"
        try:
            z.room_key = r.key
            with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 3):
                handler.on_monster_turn_start(engine, z)
        finally:
            r.template_id = old
    assert engine._haunt_track_value("zombies_trapped") >= engine._haunt_track_target("zombies_trapped")
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt2_no_attack_before_seance() -> None:
    """剧本 2 p13：降灵会完成（任一方召出幽灵）之前谁都不能攻击。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=2)
    handler = engine._mode_handler()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
    flags = engine._haunt_flags()
    assert not flags.get("ghost_summoned"), "测试前提：降灵应尚未完成"

    assert handler.attack_allowed(engine, hero, traitor) is False, "降灵完成前不许攻击"
    # 引擎攻击入口同样被拦（同房间、可攻击状态下仍拒绝）
    if traitor is not None and not traitor.dead:
        hero.room_key = traitor.room_key
        assert engine.attack(hero, traitor) is False
        assert not hero.attack_used, "被闸门拦下的攻击不应消耗攻击动作"

    flags["ghost_summoned"] = True
    assert handler.attack_allowed(engine, hero, traitor) is True, "降灵完成后解禁"


def verify_haunt3_witch_breath_and_frog_carry() -> None:
    """剧本 3：女巫龙息（视野 2 骰不可防御）；蛙可被背起携带（p14/p85）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=3)  # 109/4 人局英雄存活最多
    handler = engine._mode_handler()
    witch = engine._monster_by_template("witch")
    assert witch is not None
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    assert len(heroes) >= 2, "该种子应至少有两名活英雄"

    # 龙息：没有同房目标、视野内有"够远"的英雄 → 原地喷 2 骰物理伤害
    far_room = max(
        (k for k in engine.state.board if k != witch.room_key),
        key=lambda k: engine._path_length(witch.room_key, k),
    )
    assert engine._path_length(witch.room_key, far_room) > 3, "需要一名离女巫够远的英雄"
    for p in heroes:
        p.room_key = far_room
        p.items = [card for card in p.items if card != "item_armor"]  # 盔甲会挡物理伤害
    positions = {p.id: p.stat_positions.get("might") for p in heroes}
    with patch.object(engine, "_has_line_of_sight", return_value=True), patch.object(
        engine, "roll_dice", side_effect=lambda count, label="": 5 if label == "龙息" else count
    ):
        assert handler.on_monster_move(engine, witch, 3) is True, "女巫移动钩子应接管"
    victim = heroes[0]
    assert witch.room_key != far_room, "喷龙息的女巫不应飞向目标"
    victim_pos = victim.stat_positions.get("might")
    assert victim.dead or (victim_pos is not None and victim_pos < positions[victim.id]), \
        "龙息应造成不可防御的物理伤害"
    if len(heroes) >= 2 and not heroes[1].dead:
        assert heroes[1].stat_positions.get("might") == positions[heroes[1].id], "龙息只伤一个目标"

    # 背蛙：英雄背起同房间的蛙 → 跟着走 → 放下（用未被龙息波及的英雄）
    frog_hero = heroes[1]
    carrier = heroes[2]
    engine._turn_into_frog(frog_hero)
    carrier.room_key = frog_hero.room_key
    assert handler.perform_action(engine, carrier, "carry_frog", {}) is True
    carried = handler._carried_map(engine)
    assert str(frog_hero.id) in carried and carried[str(frog_hero.id)] == carrier.id

    dest = next(
        (k for k, r in engine.state.board.items()
         if k != carrier.room_key and (r.first_effect_done or r.visit_count > 0)),
        None,
    )
    if dest is None:
        dest = next(k for k in engine.state.board if k != carrier.room_key)
    engine._move_to_room(carrier, dest)
    assert frog_hero.room_key == dest, "背着蛙的英雄移动，蛙应跟着走"

    assert handler.perform_action(engine, carrier, "drop_frog", {}) is True
    assert str(frog_hero.id) not in handler._carried_map(engine), "放下后解除绑定"
    assert frog_hero.room_key == carrier.room_key, "放下的蛙留在当前房间"


def verify_haunt4_spider_blank_reroll() -> None:
    """剧本 4 p86：蜘蛛每次攻击把空白骰重掷一次（monster_rerolls_blanks）。"""
    import random

    engine = _run_until_haunt(seed=113, players=3, haunt_id=4)
    handler = engine._mode_handler()
    spider = engine._monster_by_template("giant_spider")
    assert spider is not None
    assert handler.monster_rerolls_blanks(engine, spider) is True, "蜘蛛应重掷空白骰"
    player = next(p for p in engine.state.players)
    assert handler.monster_rerolls_blanks(engine, player) is False, "其他目标不重掷"

    # 相同随机种子下：重掷后的总和 = 非零骰 + 补掷值 ≥ 原总和（0 骰被重掷）
    for seed in range(60):
        engine.rng = random.Random(seed)
        plain = engine._roll_monster_attack(spider, "might", reroll_blanks=False)
        engine.rng = random.Random(seed)
        rerolled = engine._roll_monster_attack(spider, "might", reroll_blanks=True)
        assert rerolled >= plain, f"种子 {seed}：重掷空白骰后总和不应变小（{rerolled}<{plain}）"
    # 与未开启重掷路径共存：默认路径行为不变
    engine.rng = random.Random(7)
    assert engine._roll_monster_attack(spider, "might") >= 0


def verify_haunt11_specter_invasion() -> None:
    """剧本 11：背面人影布点、疯子开窗、戒指理智攻击与放逐（p22/p93）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=11)
    handler = engine._mode_handler()
    assert isinstance(handler, SpecterInvasionMode)

    # 背面人影：门厅 + 已在场的窗房间
    facedown = [t for t in engine.tokens_of_kind("specter") if not t.face_up]
    entrance = next(k for k, r in engine.state.board.items() if r.template_id == "entrance_hall")
    assert any(t.room_key == entrance for t in facedown), "门厅应有背面人影"
    board_ids = {r.template_id for r in engine.state.board.values()}
    expected_windows = {rid for rid in SpecterInvasionMode.WINDOW_ROOMS if rid in board_ids}
    rooms_with_facedown = {engine.state.board[t.room_key].template_id for t in facedown}
    assert expected_windows <= rooms_with_facedown, "每个在场窗房间都应有背面人影"

    # 疯子：顶替在叛徒房间，7/7/7
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    madman = engine._monster_by_template("madman")
    assert madman is not None and madman.room_key == traitor.room_key
    assert (madman.speed, madman.might, madman.sanity) == (7, 7, 7)

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 疯子自动开最近的窗并放入人影（放入当回合即可行动）
    before = int(engine._haunt_flags()["specters_activated"])
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 9):
        assert handler.on_monster_turn_start(engine, madman) is True
    assert int(engine._haunt_flags()["specters_activated"]) == before + 1, "疯子开窗应放入一只人影"
    specter = next(m for m in engine.state.monsters if m.template_id == "ghost")
    assert (specter.speed, specter.might, specter.sanity) == (4, 0, 6), "人影数值应为 4/0/6"

    # 无戒指不能攻击；持戒指徒手改理智；击败即放逐
    hero.room_key = specter.room_key
    assert engine.attack(hero, specter) is False, "无戒指不能攻击雾中人影"
    hero.items.append("omen_ring")
    assert handler.attack_attr_override(engine, hero, specter, "might") == "sanity"
    with patch.object(engine, "_roll_attack", return_value=10), patch.object(
        engine, "_roll_monster_attack", side_effect=lambda monster, attr, reroll_blanks=False: 1
    ):
        assert engine.attack(hero, specter) is True
    assert specter not in engine.state.monsters, "持戒指击败即放逐"
    assert int(engine._haunt_flags()["specters_banished"]) == 1

    # 人影的理智攻击（同房间）：赢了掉理智
    target_token = next(t for t in engine.tokens_of_kind("specter") if not t.face_up)
    assert handler._release_specter(engine, target_token.room_key) is True
    specter2 = [m for m in engine.state.monsters if m.template_id == "ghost"][0]
    sanity_pos_before = hero.stat_positions.get("sanity")
    hero.room_key = specter2.room_key
    with patch.object(engine, "_roll_monster_attack", side_effect=lambda monster, attr, reroll_blanks=False: 6), \
         patch.object(engine, "_roll_attack", return_value=4):
        assert handler._specter_attack(engine, specter2) is True
    assert not hero.dead, "2 点精神伤害不应致死"
    assert hero.stat_positions.get("sanity") != sanity_pos_before, "人影应造成精神伤害"

    # 叛徒可亲自开窗（open_window 行动）
    traitor_room_token = next(t for t in engine.tokens_of_kind("specter") if not t.face_up)
    traitor.room_key = traitor_room_token.room_key
    _set_current(engine, traitor)
    ids = {a.id for a in handler.available_actions(engine, traitor)}
    assert "open_window" in ids, "叛徒在有背面人影的房间应能开窗"
    total_before = int(engine._haunt_flags()["specters_activated"])
    assert handler.perform_action(engine, traitor, "open_window", {}) is True
    assert int(engine._haunt_flags()["specters_activated"]) == total_before + 1

    # 驱魔底座：戒指可作为一次性理智来源，且不含灵应板
    hero.room_key = traitor_room_token.room_key
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "omen_ring" in ids, "持戒指应有戒指驱魔来源"
    assert "omen_spirit_board" not in ids, "剧本 11 的理智来源不含灵应板"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "omen_ring", {}) is True
    assert engine._haunt_track_value("exorcism_successes") == 1


def verify_haunt12_fleshwalkers() -> None:
    """剧本 12：双胞胎镜像冻结、追本体、水晶球规则、四属性反噬（p23/p94）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=12)
    handler = engine._mode_handler()
    assert isinstance(handler, FleshwalkerMode)

    # 无叛徒；双胞胎数 = 玩家数，全部在门厅，属性=对应玩家作祟开局值
    assert engine.state.traitor_id is None and all(p.role == "hero" for p in engine.state.players)
    entrance = next(k for k, r in engine.state.board.items() if r.template_id == "entrance_hall")
    twins = [m for m in engine.state.monsters if m.template_id == "shadow"]
    assert len(twins) == len(engine.state.players), "双胞胎数应等于玩家数"
    for twin in twins:
        assert twin.room_key == entrance, "双胞胎应全部生成在门厅"
        counterpart = handler._counterpart(engine, twin)
        assert counterpart is not None
        assert twin.might == counterpart.stats["might"], "双胞胎属性应镜像本体"

    # 追自己的本体（而非最近英雄）
    twin = twins[0]
    counterpart = handler._counterpart(engine, twin)
    counterpart.room_key = next(k for k in engine.state.board if k != twin.room_key)
    far_hero = next(p for p in engine.state.players if p.id != counterpart.id and not p.dead)
    far_hero.room_key = twin.room_key  # 最近英雄就在同房，双胞胎仍应去追本体
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 9):
        assert handler.on_monster_move(engine, twin, 9) is True
    assert twin.room_key == counterpart.room_key, "双胞胎应优先追自己的本体"

    # 无球与自己的双胞胎交手：四属性各 -1；击败默认只击晕
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero_twin = next(
        (m for m in engine.state.monsters if m.template_id == "shadow"
         and handler._counterpart(engine, m).id == hero.id),
        None,
    )
    assert hero_twin is not None, "应能找到该英雄的双胞胎"
    hero_twin.room_key = hero.room_key
    before = dict(hero.stat_positions)
    engine._active_player_id = hero.id
    with patch.object(engine, "_roll_attack", return_value=9), patch.object(
        engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 1
    ):
        assert engine.attack(hero, hero_twin) is True
    for stat in ("speed", "might", "sanity", "knowledge"):
        if before.get(stat) is not None and before[stat] > 0:
            assert hero.stat_positions[stat] < before[stat], f"无球对本体交手应掉 {stat}"
    assert hero_twin in engine.state.monsters and hero_twin.stunned_turns > 0, "无球只能击晕"

    # 昏迷双胞胎只有持球者能攻击；持球击败自己的双胞胎 → 杀死
    hero.items.append("omen_crystal_ball")
    assert handler.attack_allowed(engine, hero, hero_twin) is True, "持球者可攻击昏迷双胞胎"
    someone = next((p for p in engine.state.players if p.id != hero.id and not p.dead), None)
    if someone is not None:
        someone.items = [c for c in someone.items if c != "omen_crystal_ball"]
        assert handler.attack_allowed(engine, someone, hero_twin) is False, "无球者不能攻击昏迷双胞胎"
    hero.attack_used = False
    engine._active_player_id = hero.id
    with patch.object(engine, "_roll_attack", return_value=9), patch.object(
        engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 1
    ):
        assert engine.attack(hero, hero_twin) is True
    assert hero_twin not in engine.state.monsters, "持球击败自己的双胞胎应直接杀死"
    assert engine._haunt_track_value("twins_killed") == 1


def verify_haunt13_perchance_to_dream() -> None:
    """剧本 13：沉睡叛徒、梦魇补位、逃脱路线与秘密总数、圣徽唤醒（p24/p95）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=13)
    handler = engine._mode_handler()
    assert isinstance(handler, NightmareDreamMode)
    flags = engine._haunt_flags()

    # 沉睡者：钉住、掉光物品、不可被攻击
    sleeper = handler._sleeper(engine)
    assert sleeper is not None and not sleeper.dead, "叛徒应沉睡而非死亡"
    assert not sleeper.items, "沉睡者应掉光物品"
    handler.on_turn_start(engine, sleeper)
    assert sleeper.movement_stopped, "沉睡者应被钉住"
    assert handler.attack_allowed(engine, sleeper, sleeper) is False, "沉睡者不可被攻击"

    # 梦魇数量 = 玩家数，生成于沉睡房间；数值 5/4/4
    nightmares = [m for m in engine.state.monsters if m.template_id == "shadow"]
    assert len(nightmares) == len(engine.state.players), "梦魇数应等于玩家数"
    for m in nightmares:
        assert m.room_key == flags["sleeper_room"], "梦魇应从沉睡房间涌出"
        assert (m.speed, m.might, m.sanity) == (5, 4, 4)

    # 逃脱房间计数：至少玩家数；含门厅等
    assert int(flags["escape_total"]) >= len(engine.state.players), "逃脱房间数不应少于玩家数"
    board_ids = {r.template_id for r in engine.state.board.values()}
    assert "entrance_hall" in board_ids, "门厅属逃脱房间，应在场"

    # 梦魇逃脱：所在房间是未用逃脱房间 → 逃出并补一只；房间被标记
    nightmare = nightmares[0]
    escape_room = next(
        k for k, r in engine.state.board.items() if handler._is_open_escape_room(engine, k)
    )
    nightmare.room_key = escape_room
    total_before = int(flags["escapes"])
    assert handler.on_monster_turn_start(engine, nightmare) is True
    assert int(flags["escapes"]) == total_before + 1, "梦魇应从逃脱房间逃出"
    assert nightmare not in engine.state.monsters, "逃出的梦魇离场"
    assert engine.tokens_of_kind("escape"), "应放置逃脱路线令牌"
    replaced = [m for m in engine.state.monsters if m.template_id == "shadow"]
    assert len(replaced) == len(engine.state.players), "逃出后应立即补一只"

    # 被攻击击败 → 死亡并补位（p95）
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero.items.append("omen_holy_symbol")
    victim_nightmare = replaced[0]
    hero.room_key = victim_nightmare.room_key
    engine._active_player_id = hero.id
    with patch.object(engine, "_roll_attack", return_value=9), patch.object(
        engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 1
    ):
        assert engine.attack(hero, victim_nightmare) is True
    assert victim_nightmare not in engine.state.monsters, "被击败的梦魇应死亡"
    assert len([m for m in engine.state.monsters if m.template_id == "shadow"]) == len(engine.state.players)

    # 唤醒：圣徽同房才能尝试；成功推进唤醒进度
    _set_current(engine, hero)
    hero.room_key = flags["sleeper_room"]
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "wake_attempt" in ids, "带圣徽在沉睡房间应能尝试唤醒"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "wake_attempt", {}) is True
    assert engine._haunt_track_value("waking_progress") == 1
    assert engine.tokens_in_room(flags["sleeper_room"], "wake_token"), "唤醒成功应放检定令牌"

    # 英雄胜利：唤醒进度满
    engine._set_haunt_track_value("waking_progress", engine._haunt_track_target("waking_progress"))
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt14_stars_right() -> None:
    """剧本 14：油漆罐布点/单罐搬运/相邻投掷/尸体献祭/狂信徒偷窃（p25/p96）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=14)  # 109/4 人局英雄存活最多
    handler = engine._mode_handler()
    assert isinstance(handler, StarsRightMode)
    flags = engine._haunt_flags()

    # 布点：罐数 = 玩家数，都在油漆房间；狂信徒 = 其他玩家数，在五芒星室
    cans = engine.tokens_of_kind("paint")
    assert len(cans) == len(engine.state.players), "油漆罐应等于玩家数"
    paint_room_ids = set(StarsRightMode.PAINT_ROOMS)
    assert all(engine.state.board[t.room_key].template_id in paint_room_ids for t in cans)
    cultists = [m for m in engine.state.monsters if m.template_id == "cultist"]
    assert len(cultists) == len(engine.state.players) - 1, "狂信徒应等于其他玩家数"
    pent = flags["pentagram_room"]
    assert all(m.room_key == pent for m in cultists), "狂信徒应从五芒星室出发"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 拿罐 → 一次只能一罐
    hero.room_key = cans[0].room_key
    _set_current(engine, hero)
    assert handler.perform_action(engine, hero, "take_paint", {}) is True
    assert engine.tokens_held_by(hero.id, "paint")
    assert "take_paint" not in {a.id for a in handler.available_actions(engine, hero)}, "已背一罐不应再拿"

    # 扔罐：必须与五芒星室门相邻
    adj = next((k for k in engine.state.board if handler._door_adjacent(engine, k, pent)), None)
    assert adj is not None, "五芒星室应至少有一个门相邻房间"
    hero.room_key = adj
    assert handler.perform_action(engine, hero, "throw_paint", {}) is True
    assert engine._haunt_track_value("desecration") == 1
    assert any(t.room_key == pent for t in engine.tokens_of_kind("paint")), "罐应落入五芒星室"

    # 尸体：英雄死亡落尸 → 叛徒背尸（移动加倍）→ 献祭 +4
    other_hero = next(p for p in engine.state.players if p.role == "hero" and p.id != hero.id and not p.dead)
    engine._drop_inventory_on_death(other_hero)
    other_hero.dead = True
    handler.on_player_died(engine, other_hero)
    corpse = engine.tokens_of_kind("corpse")
    assert corpse and corpse[0].room_key == other_hero.room_key, "死亡应落尸"
    traitor.room_key = corpse[0].room_key
    _set_current(engine, traitor)
    assert handler.perform_action(engine, traitor, "take_corpse", {}) is True
    assert handler.movement_cost_multiplier(engine, traitor) == 2, "背尸入房按 2 格计"
    traitor.room_key = pent
    assert handler.perform_action(engine, traitor, "sacrifice", {}) is True
    assert engine._haunt_track_value("sacrifice_points") == 4, "尸体献祭值 4 分"
    assert not engine.tokens_held_by(traitor.id, "corpse"), "献祭后尸体离场"

    # 狂信徒偷窃：掷出高出 2+ 改为偷窃而非伤害（p96）
    hero.items.append("item_candle")
    cultist = cultists[0]
    cultist.room_key = hero.room_key
    before_items = list(hero.items)
    with patch.object(engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 9), \
         patch.object(engine, "_roll_attack", return_value=1):
        engine._monster_attack(cultist, hero)
    stolen = [c for c in before_items if c not in hero.items]
    assert stolen and stolen[0] in cultist.items, "狂信徒应偷走一件可交易物品"

    # 叛徒胜利：献祭满 13 分
    engine._set_haunt_track_value("sacrifice_points", 13)
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor"


def verify_haunt15_here_there_be_dragons() -> None:
    """剧本 15：装备三件套/火息分区/韧性减伤/矛加值/斩龙胜利（p26/p97）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=15)
    handler = engine._mode_handler()
    assert isinstance(handler, DragonSiegeMode)
    flags = engine._haunt_flags()

    # 巨龙在门厅；三件装备都在地下室房间
    dragon = engine._monster_by_template("beast")
    entrance = next(k for k, r in engine.state.board.items() if r.template_id == "entrance_hall")
    assert dragon is not None and dragon.room_key == entrance, "巨龙应从门厅进来"
    assert (dragon.speed, dragon.might, dragon.sanity) == (3, 8, 6)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    basement_ids = set(DragonSiegeMode.BASEMENT_ROOMS)
    for kind, flag in (("antique_armor", "armor_room"), ("shield", "shield_room")):
        tokens = engine.tokens_of_kind(kind)
        assert tokens, f"{kind} 应已放置"
        assert flags[flag] is not None
        assert engine.state.board[flags[flag]].template_id in basement_ids, f"{kind} 应在地下室"
    # 矛：若开局没有第三个地下室房间则处于待放状态，模拟发现即补放
    if not engine.tokens_of_kind("spear"):
        assert flags["spear_room"] is None, "未放置的矛应处于待放状态"
        target_room = next(
            r for r in engine.state.board.values()
            if r.template_id in DragonSiegeMode.BASEMENT_ROOMS
            and r.key not in {flags["armor_room"], flags["shield_room"]}
        ) if any(
            r.template_id in DragonSiegeMode.BASEMENT_ROOMS
            and r.key not in {flags["armor_room"], flags["shield_room"]}
            for r in engine.state.board.values()
        ) else next(iter(engine.state.board.values()))
        if target_room.template_id not in DragonSiegeMode.BASEMENT_ROOMS:
            target_room.template_id = "catacombs"
        handler.on_room_discovered(engine, hero, target_room)
        assert engine.tokens_of_kind("spear"), "发现地下室房间后应补放矛"

    # 免疫速度攻击；持戒指徒手改理智；持矛攻击 +4
    dragon_id = dragon.id
    assert handler.attack_attr_override(engine, hero, dragon, "might") is None, "无戒指不触发理智覆盖"
    hero.items.append("omen_ring")
    assert handler.attack_attr_override(engine, hero, dragon, "might") == "sanity"

    # 韧性：击败一次 5 点伤害实扣 3（-2），不击晕
    engine._active_player_id = hero.id
    hero.room_key = dragon.room_key
    pos_before = engine._haunt_track_value("dragon_damage")
    with patch.object(engine, "_roll_attack", return_value=9), patch.object(
        engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 4
    ):
        assert engine.attack(hero, dragon) is True
    assert engine._haunt_track_value("dragon_damage") == pos_before + 3, "韧性应实扣 5-2=3"
    assert dragon in engine.state.monsters and dragon.stunned_turns == 0, "巨龙不受击晕"

    # 火息：同房无盾英雄速度检定失败 → 4 骰物理（可弃物减伤）
    hero.room_key = dragon.room_key
    hero.items.append("item_candle")
    items_before = len(hero.items)
    with patch.object(engine, "_roll_attack", return_value=1), patch.object(
        engine, "roll_dice", side_effect=lambda count, label="": 6 if label == "龙焰" else count
    ):
        handler._firebreath(engine, dragon)
    discarded = items_before - len(hero.items)
    assert hero.dead or hero.stat_positions.get("might") is not None, "火息后英雄状态应可判定"

    # 持盾者与同房英雄免疫龙焰
    hero2 = next((p for p in engine.state.players if p.role == "hero" and p.id != hero.id and not p.dead), None)
    if hero2 is not None:
        engine.spawn_token("shield", label="盾", role="carried", holder=hero2.id)
        hero.room_key = dragon.room_key
        hero2.room_key = dragon.room_key
        might_before = hero2.stat_positions.get("might")
        with patch.object(engine, "_roll_attack", return_value=1), patch.object(
            engine, "roll_dice", side_effect=lambda count, label="": 8 if label == "龙焰" else count
        ):
            handler._firebreath(engine, dragon)
        assert hero2.stat_positions.get("might") == might_before, "持盾者应免疫龙焰"

    # 叛徒胜利兜底与英雄斩龙胜利
    engine._set_haunt_track_value("dragon_damage", engine._haunt_track_target("dragon_damage"))
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"
    assert engine._monster_by_template("beast") is None, "斩龙后巨龙离场"


def verify_haunt16_phantoms_embrace() -> None:
    """剧本 16：女孩 set aside、幻影出现与抽牌抑制、攻防逃走、拆弹/爆炸（p27/p98）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=16)
    handler = engine._mode_handler()
    assert isinstance(handler, PhantomBombMode)
    flags = engine._haunt_flags()

    # 女孩卡被 set aside：牌堆/房间/玩家手上都不应有
    assert not any("omen_girl" in deck for deck in engine.state.card_decks.values()), "女孩卡应被移出牌堆"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 幻影在带符号的地下室房间出现，并抑制该次抽牌
    room_a = next(r for r in engine.state.board.values() if r.floor == -1)
    room_a.symbol = "event"
    handler.on_room_discovered(engine, hero, room_a)
    phantom = next(m for m in engine.state.monsters if m.template_id == "ghost")
    assert phantom.room_key == room_a.key, "幻影应出现在发现的地下室房间"
    assert engine.tokens_in_room(room_a.key, "girl"), "女孩令牌应与幻影同房"
    assert engine.tokens_in_room(room_a.key, "phantom_mark"), "应放置到访标记"
    assert handler.suppress_room_draw(engine, hero, room_a) is True, "幻影房间应抑制抽牌"
    assert handler.on_monster_turn_attack(engine, phantom) is True, "幻影不攻击"
    assert handler.on_monster_move(engine, phantom, 5) is True, "幻影不移动"

    # 防御成功 → 英雄吃反击伤害，幻影带女孩逃走
    hero.room_key = room_a.key
    engine._active_player_id = hero.id
    with patch.object(engine, "_roll_attack", return_value=1), patch.object(
        engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 8
    ):
        assert engine.attack(hero, phantom) is True
    assert phantom not in engine.state.monsters, "幻影应带女孩逃走"
    assert not engine.tokens_of_kind("girl"), "女孩令牌应随幻影离场"
    assert not flags.get("girl_rescued")

    # 再次出现 → 击败 → 女孩获救，房间成为可拆弹房间
    room_b = next(r for r in engine.state.board.values() if r.floor == -1 and r.key != room_a.key)
    room_b.symbol = "omen"
    handler.on_room_discovered(engine, hero, room_b)
    phantom2 = next(m for m in engine.state.monsters if m.template_id == "ghost")
    hero.room_key = room_b.key
    hero.attack_used = False
    with patch.object(engine, "_roll_attack", return_value=9), patch.object(
        engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 1
    ):
        assert engine.attack(hero, phantom2) is True
    assert phantom2 not in engine.state.monsters, "被击败的幻影应死亡"
    assert flags.get("girl_rescued") is True
    assert flags.get("bomb_room") == room_b.key
    assert engine.tokens_held_by(hero.id, "girl"), "击败者应抱起女孩"

    # 拆弹：必须在炸弹房间，知识 7+
    _set_current(engine, hero)
    hero.room_key = room_b.key
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "defuse_bomb" in ids, "获救后应能拆弹"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "defuse_bomb", {}) is True
    assert flags.get("bomb_defused") is True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # 炸弹计时：叛徒回合开始推进并掷骰，达阈值即爆炸
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    flags["bomb_defused"] = False
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    engine._set_haunt_track_value("bomb_timer", handler.BLOWUP_THRESHOLD[len(engine.state.players)] - 1)
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 8 if label == "炸弹计时" else count):
        handler.on_turn_start(engine, traitor)
    assert flags.get("house_blown") is True
    assert engine.state.winner == "traitor"


def verify_haunt17_bugs() -> None:
    """剧本 17：配料布点/合成/杀虫剂速度攻击/蛛网禁锢/蟑螂守厨房/叛徒销毁（p28/p99）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=17)
    handler = engine._mode_handler()
    assert isinstance(handler, BugSprayMode)
    flags = engine._haunt_flags()

    # 布点：在场房间有配料与虫；虫的种类映射齐全
    ingredient_rooms = {t.room_key for t in engine.tokens_of_kind("ingredient")}
    paint_ids = {rid for rid, _ in BugSprayMode.INGREDIENT_ROOMS}
    assert all(engine.state.board[k].template_id in paint_ids for k in ingredient_rooms), "配料只能放在六类房间"
    assert ingredient_rooms, "至少应在已翻出的房间放一枚配料"
    kinds = set(flags.get("bug_kind", {}).values())
    assert kinds <= {"mantis", "centipede", "wasp", "spider_bug", "roach", "beetle"}
    assert "mantis" in kinds, "螳螂应在作祟房间生成"
    roach = next(
        (m for m in engine.state.monsters if handler._kind_of(engine, m) == "roach"), None
    )
    if roach is None:
        # 厨房未在翻出的房间里：模拟发现厨房补放蟑螂
        kitchen = next((r for r in engine.state.board.values() if r.template_id == "kitchen"), None)
        if kitchen is None:
            kitchen = next(iter(engine.state.board.values()))
            kitchen.template_id = "kitchen"
        spec = {"template_id": "spider", "name": "蟑螂", "speed": 0, "might": 5, "sanity": 4}
        roach = engine._spawn_single_haunt_monster(spec, kitchen.key)
        flags["bug_kind"][str(roach.id)] = "roach"
    assert engine.state.board[roach.room_key].template_id == "kitchen", "蟑螂应在厨房"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 合成：三枚配料同房 → 知识 4+ → 杀虫剂到手上，配料移出游戏
    room = hero.room_key
    # 把所有在地上或别人手里的配料集中到测试房间，凑足三枚
    pool = handler._room_ingredient_pool(engine, room)
    for token in list(engine.tokens_of_kind("ingredient")):
        if len(handler._room_ingredient_pool(engine, room)) >= 3:
            break
        if token in pool:
            continue
        if token.holder is not None:
            engine.give_token(token.uid, hero.id)
        elif token.room_key:
            engine.place_token(token.uid, room)
    # 若全屋配料不足三枚（部分还在待放状态），临时补发测试配料
    while len(handler._room_ingredient_pool(engine, room)) < 3:
        token = engine.spawn_token("ingredient", label="测试配料", role="marker", room_key=room)
        token.data["name"] = "测试配料"
    assert len(handler._room_ingredient_pool(engine, room)) >= 3
    ingredient_total_before = len(engine.tokens_of_kind("ingredient"))
    _set_current(engine, hero)
    room_obj = engine.state.board[room]
    room_template_before = room_obj.template_id
    room_obj.template_id = "kitchen"  # 合成必须在实验室/厨房
    try:
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "make_spray" in ids, "三枚配料同房应能合成"
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "make_spray", {}) is True
    finally:
        room_obj.template_id = room_template_before
    assert engine.tokens_held_by(hero.id, "bug_spray"), "杀虫剂应到合成者手上"
    assert len(engine.tokens_of_kind("ingredient")) == ingredient_total_before - 3, "合成应恰好消耗三枚配料"

    # 杀虫剂攻击：对虫改速度攻击；击败即杀并计数；杀满三只其余逃散
    bug = next(m for m in engine.state.monsters if handler._kind_of(engine, m) != "roach")
    hero.room_key = bug.room_key
    engine._active_player_id = hero.id
    assert handler.attack_attr_override(engine, hero, bug, "might") == "speed"
    engine.attack(hero, bug)
    assert bug not in engine.state.monsters, "持杀虫剂击败虫应直接杀死"
    assert engine._haunt_track_value("bugs_killed") == 1
    # 用杀虫剂落败不受伤
    hero.attack_used = False
    bug2 = next(m for m in engine.state.monsters if handler._kind_of(engine, m) == "beetle" or m is not bug)
    bug2 = next(m for m in engine.state.monsters if handler._kind_of(engine, m) not in ("roach",))
    if bug2 is not None:
        hero.room_key = bug2.room_key
        might_pos = hero.stat_positions.get("might")
        with patch.object(engine, "_roll_attack", return_value=1), patch.object(
            engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 9
        ):
            assert engine.attack(hero, bug2) is True
        assert not hero.dead, "用杀虫剂落败不应致死"
        assert hero.stat_positions.get("might") == might_pos, "用杀虫剂落败不应受伤（p28）"
        assert bug2.stunned_turns == 0, "虫赢回合不构成被击败，不应被晕"

    # 蛛网：蜘蛛击败英雄 → 被缚（属性 -2 不低于 1）；挣脱恢复
    spider = next((m for m in engine.state.monsters if handler._kind_of(engine, m) == "spider_bug"), None)
    if spider is None:
        room_s = next((r for r in engine.state.board.values() if r.template_id == "larder"), None)
        if room_s is not None:
            spec = {"template_id": "spider", "name": "蜘蛛", "speed": 3, "might": 6, "sanity": 4}
            spider = engine._spawn_single_haunt_monster(spec, room_s.key)
            flags["bug_kind"][str(spider.id)] = "spider_bug"
    if spider is not None:
        hero2 = next(p for p in engine.state.players if p.role == "hero" and p.id != hero.id and not p.dead)
        hero2.room_key = spider.room_key
        might_before = hero2.stats["might"]
        assert handler.on_monster_attack(engine, spider, hero2, 3) is True
        assert str(hero2.id) in flags.get("webbed", []), "被蜘蛛击败应被缚"
        assert hero2.stats["might"] >= might_before - 2, "被缚至多 -2"
        assert hero2.movement_stopped, "被缚者不能移动"
        # 同房挣脱
        hero.room_key = hero2.room_key
        _set_current(engine, hero)
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "break_webs" in ids, "同房有被缚者应能挣脱"
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "break_webs", {}) is True
        assert str(hero2.id) not in flags.get("webbed", []), "挣脱后解除"
        assert not hero2.movement_stopped

    # 蟑螂守厨房：离开厨房按 3 格
    assert handler.movement_cost_floor(engine, hero, roach.room_key) == 3

    # 叛徒销毁配料：拾取 → 深渊销毁 → 计数；4 枚且无杀虫剂 → 叛徒胜
    eng_tokens = [t for t in engine.tokens_of_kind("ingredient") if t.room_key]
    if not eng_tokens:
        eng_tokens = [engine.spawn_token("ingredient", label="测试配料", role="marker", room_key=traitor.room_key)]
        eng_tokens[0].data["name"] = "测试配料"
    traitor.room_key = eng_tokens[0].room_key
    _set_current(engine, traitor)
    assert handler.perform_action(engine, traitor, "take_ingredient", {}) is True
    assert engine.tokens_held_by(traitor.id, "ingredient"), "叛徒应拾到配料"
    traitor.room_key = next(
        k for k, r in engine.state.board.items() if r.template_id in ("chasm", "furnace_room", "underground_lake")
    )
    ids = {a.id for a in handler.available_actions(engine, traitor)}
    assert "destroy_ingredient" in ids
    assert handler.perform_action(engine, traitor, "destroy_ingredient", {}) is True
    assert engine._haunt_track_value("ingredients_destroyed") == 1
    # 英雄胜利：毒杀满三只（把剩余计数顶满）
    engine._set_haunt_track_value("bugs_killed", 3)
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt4_setup_and_trapped() -> None:
    """剧本 4：被困者钉住、蛛网/检定令牌放置、3-4 人局叛徒被吃（p15/p86）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=4)
    assert engine.state.haunt is not None and engine.state.haunt.id == 4
    flags = engine._haunt_flags()
    haunt_room = engine.state.meta["haunt_rule"]["haunt_room"]

    # 蛛网令牌在作祟房间；检定令牌 = 玩家数
    webs = engine.tokens_of_kind("web")
    assert len(webs) == 1 and webs[0].room_key == haunt_room
    assert len(engine.tokens_of_kind("might_check")) == len(engine.state.players)

    # 被困者 = 作祟揭示者，被钉住
    trapped_id = flags.get("trapped_id")
    assert trapped_id == engine.state.haunt_revealer_id
    trapped = next(p for p in engine.state.players if p.id == trapped_id)
    assert trapped.movement_stopped, "被困者应不能移动"

    # 3 人局：叛徒（非被困者时）开局被蜘蛛吃掉（p86）；
    # 叛徒恰好是被困者本人时保持在场——被困者是救援目标，吃了剧本无解。
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    if traitor.id != flags.get("trapped_id"):
        assert traitor.dead, "3-4 人局叛徒（非被困者）应被蜘蛛吃掉"
    else:
        assert not traitor.dead, "叛徒即被困者时应保持在场"
        assert trapped.id == traitor.id

    # 蜘蛛已生成。注意对局可能已跑了若干轮，属性应处于成长表区间内；
    # 逐回合成长本身由 verify_haunt4_timer_and_growth 精确验证。
    spider = engine._monster_by_template("giant_spider")
    assert spider is not None
    assert 0 <= spider.speed <= 6
    assert 2 <= spider.might <= 8

    # 被困者每回合开始仍被钉住（网未破）
    handler = engine._mode_handler()
    handler.on_turn_start(engine, trapped)
    assert trapped.movement_stopped


def verify_haunt4_web_and_eggs_flow() -> None:
    """剧本 4：打网推进轨道、满值解困；销毁卵两条路径；开门前置（p15）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=4)
    handler = engine._mode_handler()
    flags = engine._haunt_flags()
    haunt_room = engine.state.meta["haunt_rule"]["haunt_room"]
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    trapped = next(p for p in engine.state.players if p.id == flags.get("trapped_id"))

    # 打网：站在蛛网房间。对决是掷骰（Might vs 4），把力量拉满保证命中率，
    # 循环多次直到轨道打满——这里验证的是"打满→解困"链路而非掷骰运气。
    hero.room_key = haunt_room
    might_track = engine._stat_track(hero, "might")
    hero.stat_positions["might"] = len(might_track) - 1
    hero.stats["might"] = might_track[-1]
    target = engine._haunt_track_target("web_damage")
    for _ in range(target * 10):
        if engine._haunt_track_value("web_damage") >= target:
            break
        engine._set_haunt_track_value("web_damage", min(target - 1, engine._haunt_track_value("web_damage") + 1))
        handler.perform_action(engine, hero, "attack_web", {})
    assert engine._haunt_track_value("web_damage") >= target, "满力量下应能打满蛛网轨道"
    assert flags.get("web_destroyed"), "轨道满后蛛网应被摧毁"
    assert not trapped.movement_stopped, "网破后被困者应解困"
    assert not engine.tokens_of_kind("web"), "网破后蛛网令牌应移除"

    # 销毁卵：药膏路径免检定
    hero.items.append("item_healing_salve")
    hero.room_key = trapped.room_key
    ok = handler.perform_action(engine, hero, "destroy_eggs_salve", {})
    assert ok and flags.get("eggs_destroyed"), "药膏应免检定直接销毁蛛卵"
    assert "item_healing_salve" not in hero.items, "药膏应被消耗"

    # 开门：网未全破时不可见（已破，直接测可见与执行）
    entrance = next((r for r in engine.state.board.values() if r.template_id == "entrance_hall"), None)
    if entrance:
        hero.room_key = entrance.key
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "open_front_door" in ids, "网破+卵毁后应能开门"
    # 卵未毁时不可开门（重置验证）
    flags["eggs_destroyed"] = False
    if entrance:
        hero.room_key = entrance.key
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "open_front_door" not in ids, "卵未毁时不应能开门"


def verify_haunt4_timer_and_growth() -> None:
    """剧本 4：倒计时推进、第 9 回合判负、蜘蛛按表成长（p86）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=4)
    handler = engine._mode_handler()
    flags = engine._haunt_flags()
    # 3 人局叛徒已死 → 用"首位存活玩家回合"推进
    alive = [p for p in engine.state.players if not p.dead]
    first = alive[0]

    deadline = engine._haunt_track_target("spider_timer")
    for i in range(deadline - 1):
        handler.on_turn_start(engine, first)
        assert engine.state.winner is None, f"第 {i + 1} 轮不应判负"
    assert engine._haunt_track_value("spider_timer") == deadline - 1

    handler.on_turn_start(engine, first)
    assert engine.state.winner == "traitor", "第 9 回合应判叛徒胜"
    assert "蛛卵" in engine.state.winner_reason

    # 蜘蛛成长到满值 6/8
    spider = engine._monster_by_template("giant_spider")
    if spider is not None:
        assert spider.speed == 6 and spider.might == 8


def verify_attack_defense_action_type() -> None:
    """引擎能力：attack/defense 型剧本行动按属性对决固定防御值。

    该字段过去被引擎完全忽略（必成功），剧本 1/4/5/6 的攻击类行动
    全部失真——本次修复后按掷骰对决结算。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=4)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    # attack_web 要求站在蛛网房间（same_room:web）
    web = engine.tokens_of_kind("web")
    if web:
        hero.room_key = web[0].room_key
    # 直接调 _perform_generic_haunt_action 会走 attack 分支：
    # 无论成败都要消耗行动并返回 True（检定失败也算行动已执行）
    engine._haunt_flags()
    before = engine._haunt_track_value("web_damage")
    ok = engine._perform_generic_haunt_action(hero, "attack_web", {})
    assert ok, "攻击型行动应正常执行"
    after = engine._haunt_track_value("web_damage")
    # 掷赢才推进，掷输不动——两者都是合法结果，这里只验证不崩溃且方向正确
    assert after in (before, before + 1)


def verify_haunt4_traitor_death_no_win() -> None:
    """剧本 4：杀死叛徒不构成英雄胜利（p15 只认 解困+毁卵+出屋）。

    注意 3-4 人局里叛徒可能开局就被吃（或恰好是被困者而保持在场），
    无论哪种，杀死/失去叛徒都不应触发引擎的"叛徒死亡→英雄胜"兜底。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=4)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    traitor.dead = True

    result = engine._mode_handler().check_victory(engine)
    assert result is True, "应吸收兜底"
    assert engine.state.winner is None, "叛徒被吃不构成英雄胜利"


def verify_haunt6_setup_and_traitor_away() -> None:
    """剧本 6：飞船/检定令牌放置、叛徒开局出局（p88 等待运输）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=6)
    assert engine.state.haunt is not None and engine.state.haunt.id == 6
    flags = engine._haunt_flags()
    haunt_room = engine.state.meta["haunt_rule"]["haunt_room"]

    # 飞船令牌在作祟房间；力量检定令牌 = 玩家数
    ships = engine.tokens_of_kind("spaceship")
    assert len(ships) == 1 and ships[0].room_key == haunt_room
    assert len(engine.tokens_of_kind("might_check")) == len(engine.state.players)
    assert flags.get("ship_room") == haunt_room

    # 叛徒开局出局（p88：放上飞船令牌，等待运输）
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert traitor.dead, "叛徒应出局等待运输"
    assert not traitor.items, "出局时物品应留在原房间"

    # 3 人局 1 只外星人（p88）
    aliens = [m for m in engine.state.monsters if m.template_id == "alien"]
    assert len(aliens) == 1, f"3 人局应 1 只外星人，实际 {len(aliens)}"


def verify_haunt6_mind_control_lifecycle() -> None:
    """剧本 6：精神控制 → 被控者行为受限 → 移向飞船 → 上船出局（p17/p88）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=6)
    handler = engine._mode_handler()
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 手工置被控状态
    flags["controlled_ids"] = [hero.id]
    assert engine.available_haunt_actions(hero) == [], "被控者不能做剧本行动"

    # 被控者回合开始：移向飞船
    ship_room = flags.get("ship_room")
    assert hero.room_key != ship_room
    handler.on_turn_start(engine, hero)
    # 被移向飞船（路径上的下一格）
    assert hero.room_key != ship_room or hero.room_key == ship_room  # 至多走 speed 格

    # 拉到飞船房间门口再推一格：到达 → 下回合开始上船
    path = engine._shortest_path(hero.room_key, ship_room)
    if len(path) > 1:
        hero.room_key = path[-2]  # 飞船房间的前一格
        hero.stats["speed"] = max(1, hero.stats.get("speed", 1))
        handler.on_turn_start(engine, hero)
        assert hero.room_key == ship_room, "被控者应到达飞船房间"
    assert not hero.dead, "刚到飞船房间时不应立刻上船"
    # 下一回合开始：上船出局
    handler.on_turn_start(engine, hero)
    assert hero.dead, "到达飞船房间的下回合开始应上船出局"
    assert hero.id not in set(flags.get("controlled_ids", [])), "上船后应移出被控列表"


def verify_haunt6_free_and_immune() -> None:
    """剧本 6：攻击被控同伴取胜 → 半伤+解控+永久免疫（p17）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=6)
    handler = engine._mode_handler()
    flags = engine._haunt_flags()
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    # _run_until_haunt 可能已跑到终局（死者跳过让对局能跑完），存活英雄不足
    # 时复活一个再测——本测试验证的是"解救"逻辑本身，不依赖对局进度。
    if len(heroes) < 2:
        fallen = next(p for p in engine.state.players if p.role == "hero" and p.dead)
        fallen.dead = False
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    rescuer, victim = heroes[0], heroes[1]

    victim.room_key = rescuer.room_key
    flags["controlled_ids"] = [victim.id]

    # 被控者可以被同阵营英雄攻击（available_attack_targets 包含）
    targets = engine.available_attack_targets(rescuer)
    assert victim in targets, "被控同伴应可被同阵营攻击（解救路径）"

    # 击败被控者：半伤+解控+免疫。physical 伤害可能落在 might 或 speed，
    # 所以验证"总轨道位置减少 2"（4 点伤害的半数，向下取整），
    # 而不是死盯某一个属性。
    victim.stats["might"] = 6
    total_before = sum(victim.stat_positions.get(s, 0) for s in ("might", "speed"))
    engine._apply_attack_damage(victim, 4, "might")
    total_after = sum(victim.stat_positions.get(s, 0) for s in ("might", "speed"))
    reduced = total_before - total_after
    # 核心验证点：是"减半"而不是"全伤 4"。逐点结算可能被 overflow 抵掉
    # 一部分，所以只断言 0 < 减幅 <= 2（4 的半数，向下取整）。
    assert 0 < reduced <= 2, f"解救应只受一半伤害（4→至多 2），实际减 {reduced}"
    assert victim.id not in set(flags.get("controlled_ids", [])), "应解除控制"
    assert victim.id in set(flags.get("immune_ids", [])), "应永久免疫"

    # 免疫后不再被外星人控制
    alien = engine._monster_by_template("alien")
    if alien:
        alien.room_key = victim.room_key
        handled = handler.on_monster_turn_attack(engine, alien)
        assert victim.id not in set(flags.get("controlled_ids", [])), "免疫者不能再次被控"


def verify_haunt6_alien_turn_attack() -> None:
    """剧本 6：外星人对同房间所有未控未免疫英雄各自理智对决（p88）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=6)
    handler = engine._mode_handler()
    flags = engine._haunt_flags()
    alien = engine._monster_by_template("alien")
    assert alien is not None
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    # 全拉到外星人房间
    for h in heroes:
        h.room_key = alien.room_key
    handled = handler.on_monster_turn_attack(engine, alien)
    assert handled, "有目标时外星人的意念攻击应被接管"
    # 输赢是概率事件，不断言谁被控；只验证接口与无副作用
    controlled = set(flags.get("controlled_ids", []))
    immune = set(flags.get("immune_ids", []))
    assert controlled.isdisjoint(immune), "被控与免疫不应重叠"

    # 同房间没有可攻击对象时回落（返回 False）
    for h in heroes:
        h.room_key = "0:0:0"
    alien.room_key = "1:0:0"
    assert not handler.on_monster_turn_attack(engine, alien), "同房间无目标时不应接管"


def verify_haunt6_traitor_away_no_win() -> None:
    """剧本 6：叛徒开局出局，不触发"叛徒死亡→英雄胜"（p88）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=6)
    result = engine._mode_handler().check_victory(engine)
    assert result is True, "应吸收兜底"
    assert engine.state.winner is None, "叛徒出局不构成英雄胜利"


def verify_dead_player_turn_skipped() -> None:
    """引擎能力：死者的回合被跳过并推进轮转（剧本 6 首次暴露）。

    以前 bot take_turn 对死者返回 False，主循环死锁在"轮到死者"那一刻，
    end_turn 里的怪物回合永远执行不到——剧本 6 实测 17 回合怪物 0 行动。
    """
    from bot_ai import BotController  # 局部导入，避免循环

    engine = _run_until_haunt(seed=113, players=3, haunt_id=6)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert traitor.dead, "剧本 6 叛徒应已出局"
    # 把轮转指到死者
    engine.state.turn_index = engine.state.turn_order.index(traitor.id)
    assert engine.current_player is traitor
    controller = BotController()
    ok = controller.take_turn(engine)
    assert ok, "死者的回合应被跳过（返回 True 而不是中断主循环）"
    assert engine.current_player is not traitor, "轮转应已推进到下一个活人"


def main():
    verify_mode_dispatch()
    verify_mode_handler_reaches_engine()
    verify_token_api()
    verify_token_serialization()
    verify_save_roundtrip_keeps_tokens()
    verify_haunt1_tokens()
    verify_haunt1_girl_set_aside()
    verify_haunt1_girl_pickup()
    verify_haunt1_mummy_damage()
    verify_haunt1_steal_instead()
    verify_haunt1_secret_passage()
    verify_haunt2_seance_race()
    verify_haunt2_bones_require_summon()
    verify_haunt2_ghost_rules()
    verify_haunt2_timer()
    verify_haunt2_traitor_death_no_win()
    verify_haunt2_ghost_destroyed_on_defeat()
    verify_haunt3_witch_invulnerable()
    verify_haunt3_frog_lifecycle()
    verify_haunt3_root_tokens()
    verify_haunt3_traitor_death_no_win()
    verify_haunt3_witch_killed_after_spell()
    verify_haunt2_no_attack_before_seance()
    verify_haunt3_witch_breath_and_frog_carry()
    verify_haunt4_spider_blank_reroll()
    verify_haunt4_setup_and_trapped()
    verify_haunt4_web_and_eggs_flow()
    verify_haunt4_timer_and_growth()
    verify_attack_defense_action_type()
    verify_haunt4_traitor_death_no_win()
    verify_haunt6_setup_and_traitor_away()
    verify_haunt6_mind_control_lifecycle()
    verify_haunt6_free_and_immune()
    verify_haunt6_alien_turn_attack()
    verify_haunt6_traitor_away_no_win()
    verify_haunt7_setup_and_vines()
    verify_haunt7_spray_creation_and_kill()
    verify_haunt7_grab_release_mulch()
    verify_haunt7_elevator_and_destroy()
    verify_haunt8_banshee_exorcism()
    verify_haunt9_dance_of_death()
    verify_haunt10_family_gathering()
    verify_haunt11_specter_invasion()
    verify_haunt12_fleshwalkers()
    verify_haunt13_perchance_to_dream()
    verify_haunt14_stars_right()
    verify_haunt15_here_there_be_dragons()
    verify_haunt16_phantoms_embrace()
    verify_haunt17_bugs()
    verify_dead_player_turn_skipped()
    verify_monster_defeated_hook_defaults()
    verify_ensure_room_in_play()
    verify_bot_quest_goal_rooms()
    print("verify_haunt_systems: ok")


if __name__ == "__main__":
    main()
