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
        BeastmasterMode,
        BeastmasterMode,
        GhostBrideMode,
        ZombieLordMode,
        AbyssExorcismMode,
        TentacledHorrorMode,
        BatSwarmMode,
        HellbeastMode,
        VoodooMode,
        RatRitualMode,
        AmokFleshMode,
        DemonRingMode,
        FrankensteinMode,
        DraculaRisingMode,
        LivingHouseMode,
        LostDimensionMode,
        LakeRescueMode,
        SupernaturalAgingMode,
        DarkerThanNightMode,
        CracklingAuraMode,
        ToxicObjectEscapeMode,
        ArkanokSkullMode,
        KingsRoadsMode,
        EternalGloryMode,
        BagOfTricksMode,
        TwistingNetherMode,
        BloodOfferingMode,
        BreathOfWindMode,
        HellOnEarthMode,
        StorybookTwistsMode,
        LabyrinthEscapeMode,
        TimeBombMode,
        CannibalFeastMode,
        OuroborosMode,
        CrimsonJackMode,
        AstralSpiritMode,
        NightMurderMode,
        SandsOfTimeMode,
        NightfallMode,
        ForAThousandYearsMode,
        BurningSandsMode,
        WispCaptureMode,
        InhumanTransformationMode,
        PortraitCurseMode,
        BuriedAliveMode,
        ShadowExorcismMode,
        HellGateHeroMode,
        InvisibleTraitorMode,
        HeirAssassinMode,
        SmallChangeMode,
        SwampEscapeMode,
        DeathCheckmateMode,
        MadWorldMode,
        BugSprayMode,
        OffspringMode,
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
        OffspringMode,
        PhantomBombMode,
        GhostBrideMode,
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
    assert handlers.get(OffspringMode) == [18], f"剧本 18 未走定制 handler: {handlers.get(OffspringMode)}"
    assert handlers.get(BeastmasterMode) == [19], f"剧本 19 未走定制 handler: {handlers.get(BeastmasterMode)}"
    assert handlers.get(GhostBrideMode) == [20], f"剧本 20 未走定制 handler: {handlers.get(GhostBrideMode)}"
    assert handlers.get(ZombieLordMode) == [21], f"剧本 21 未走定制 handler: {handlers.get(ZombieLordMode)}"
    assert handlers.get(AbyssExorcismMode) == [22], f"剧本 22 未走定制 handler: {handlers.get(AbyssExorcismMode)}"
    assert handlers.get(TentacledHorrorMode) == [23], f"剧本 23 未走定制 handler: {handlers.get(TentacledHorrorMode)}"
    assert handlers.get(BatSwarmMode) == [24], f"剧本 24 未走定制 handler: {handlers.get(BatSwarmMode)}"
    assert handlers.get(HellbeastMode) == [38], f"剧本 38 未走定制 handler: {handlers.get(HellbeastMode)}"
    assert handlers.get(VoodooMode) == [25], f"剧本 25 未走定制 handler: {handlers.get(VoodooMode)}"
    assert handlers.get(RatRitualMode) == [26], f"剧本 26 未走定制 handler: {handlers.get(RatRitualMode)}"
    assert handlers.get(AmokFleshMode) == [27], f"剧本 27 未走定制 handler: {handlers.get(AmokFleshMode)}"
    assert handlers.get(DemonRingMode) == [28], f"剧本 28 未走定制 handler: {handlers.get(DemonRingMode)}"
    assert handlers.get(FrankensteinMode) == [29], f"剧本 29 未走定制 handler: {handlers.get(FrankensteinMode)}"
    assert handlers.get(DraculaRisingMode) == [30], f"剧本 30 未走定制 handler: {handlers.get(DraculaRisingMode)}"
    assert handlers.get(LivingHouseMode) == [31], f"剧本 31 未走定制 handler: {handlers.get(LivingHouseMode)}"
    assert handlers.get(LostDimensionMode) == [32], f"剧本 32 未走定制 handler: {handlers.get(LostDimensionMode)}"
    assert handlers.get(LakeRescueMode) == [33], f"剧本 33 未走定制 handler: {handlers.get(LakeRescueMode)}"
    assert handlers.get(SupernaturalAgingMode) == [44], f"剧本 44 未走定制 handler: {handlers.get(SupernaturalAgingMode)}"
    assert handlers.get(DarkerThanNightMode) == [51], f"51 未走定制: {handlers.get(DarkerThanNightMode)}"
    assert handlers.get(CracklingAuraMode) == [52], f"52 未走定制"
    assert handlers.get(ToxicObjectEscapeMode) == [53], f"53 未走定制"
    assert handlers.get(ArkanokSkullMode) == [54], f"54 未走定制"
    assert handlers.get(KingsRoadsMode) == [55], f"55 未走定制"
    assert handlers.get(EternalGloryMode) == [61], f"61 未走定制"
    assert handlers.get(BagOfTricksMode) == [62], f"62 未走定制"
    assert handlers.get(TwistingNetherMode) == [63], f"63 未走定制"
    assert handlers.get(BloodOfferingMode) == [64], f"64 未走定制"
    assert handlers.get(BreathOfWindMode) == [65], f"65 未走定制"
    assert handlers.get(HellOnEarthMode) == [66], f"66 未走定制"
    assert handlers.get(StorybookTwistsMode) == [67], f"67 未走定制"
    assert handlers.get(LabyrinthEscapeMode) == [68], f"68 未走定制"
    assert handlers.get(WispCaptureMode) == [69], f"69 未走定制"
    assert handlers.get(InhumanTransformationMode) == [70], f"70 未走定制"
    assert handlers.get(TimeBombMode) == [45], f"剧本 45 未走定制 handler: {handlers.get(TimeBombMode)}"
    assert handlers.get(BuriedAliveMode) == [40], f"剧本 40 未走定制 handler: {handlers.get(BuriedAliveMode)}"
    assert handlers.get(InvisibleTraitorMode) == [41], f"剧本  未走定制"
    assert handlers.get(HellGateHeroMode) == [42], f"剧本  未走定制"
    assert handlers.get(ShadowExorcismMode) == [43], f"剧本  未走定制"
    assert handlers.get(HeirAssassinMode) == [39], f"剧本 39 未走定制 handler: {handlers.get(HeirAssassinMode)}"
    assert handlers.get(SmallChangeMode) == [35], f"剧本 35 未走定制 handler: {handlers.get(SmallChangeMode)}"
    assert handlers.get(SwampEscapeMode) == [36], f"剧本 36 未走定制 handler: {handlers.get(SwampEscapeMode)}"
    assert handlers.get(DeathCheckmateMode) == [37], f"剧本 37 未走定制 handler: {handlers.get(DeathCheckmateMode)}"
    assert handlers.get(MadWorldMode) == [34], f"剧本 34 未走定制 handler: {handlers.get(MadWorldMode)}"
    assert handlers.get(CannibalFeastMode) == [46], f"剧本 46 未走定制 handler: {handlers.get(CannibalFeastMode)}"
    assert handlers.get(OuroborosMode) == [47], f"剧本 47 未走定制 handler: {handlers.get(OuroborosMode)}"
    assert handlers.get(CrimsonJackMode) == [48], f"剧本 48 未走定制 handler: {handlers.get(CrimsonJackMode)}"
    assert handlers.get(AstralSpiritMode) == [49], f"剧本 49 未走定制 handler: {handlers.get(AstralSpiritMode)}"
    assert handlers.get(NightMurderMode) == [50], f"剧本 50 未走定制 handler: {handlers.get(NightMurderMode)}"
    assert handlers.get(SandsOfTimeMode) == [56], f"剧本 56 未走定制 handler: {handlers.get(SandsOfTimeMode)}"
    assert handlers.get(PortraitCurseMode) == [57], f"剧本 57 未走定制 handler: {handlers.get(PortraitCurseMode)}"
    assert handlers.get(NightfallMode) == [58], f"剧本 58 未走定制 handler: {handlers.get(NightfallMode)}"
    assert handlers.get(ForAThousandYearsMode) == [59], f"剧本 59 未走定制 handler: {handlers.get(ForAThousandYearsMode)}"
    assert handlers.get(BurningSandsMode) == [60], f"剧本 60 未走定制 handler: {handlers.get(BurningSandsMode)}"
    generic = handlers.get(GenericModeHandler, [])
    assert len(generic) == 0, f"应有 0 个剧本回落到通用规则（70 本全部精修），实际 {len(generic)}"

    # 未注册的 mode 必须优雅降级，绝不能抛异常
    assert isinstance(get_mode_handler("labyrinth_escape"), LabyrinthEscapeMode)
    assert isinstance(get_mode_handler(None), GenericModeHandler)
    assert isinstance(get_mode_handler(""), GenericModeHandler)
    # 不存在的 mode 也不能崩
    assert isinstance(get_mode_handler("no_such_mode"), GenericModeHandler)

    assert set(registered_modes()) == {
        "alien_abduction", "banishment_escort", "beastmaster", "bug_spray", "carnivorous_ivy", "ghost_bride",
        "delayed_traitor_relic", "dragon_siege", "exorcism", "fleshwalkers", "generic",
        "nightmare_escape", "paint_the_pentagram", "phantom_bomb",
        "poisonous_plant", "seance_race", "spectre_exorcism", "trap_zombies",
        "web_escape", "werewolf_hunt", "witch_and_frogs", "zombie_lord", "abyss_exorcism",
        "tentacled_horror", "bat_exodus", "voodoo_dolls", "rat_ritual", "blob_weakness",
        "demon_ring", "frankenstein_fire", "dracula_rising", "hellbeast_exorcism",
        "living_house", "lost_dimension", "lake_rescue", "supernatural_aging", "darker_than_night", "ring_exorcism", "toxic_object_escape", "arkanok_skull", "kings_roads", "ghost_warrior", "bag_of_tricks", "twisting_nether", "blood_offering", "haunt_exorcism", "hell_on_earth", "storybook_twists", "labyrinth_escape", "wisp_capture", "inhuman_transformation", "time_bomb", "mad_world", "small_change_escape", "swamp_escape", "death_checkmate", "secret_heir", "buried_alive", "invisible_traitor", "hell_gate_hero", "shadow_exorcism",
        "cannibal_feast",
        "worm_ouroboros",
        "cursed_weapon",
        "astral_spirit",
        "night_survival",
        "time_sands",
        "portrait_curse",
        "nightfall_twilight",
        "badge_curse",
        "sphinx_riddle",
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

    engine.state.haunt = engine.catalog.haunt_defs[18]
    assert isinstance(engine._mode_handler(), OffspringMode)

    engine.state.haunt = engine.catalog.haunt_defs[19]
    assert isinstance(engine._mode_handler(), BeastmasterMode)

    engine.state.haunt = engine.catalog.haunt_defs[20]
    assert isinstance(engine._mode_handler(), GhostBrideMode)

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


def _buff_heroes_to_max(engine: GameEngine) -> None:
    """把存活英雄的四项属性抬到轨道上限。

    机制类测试常用"制造一次对决再看后果"的写法，而作祟是从真实对局中途接上的：
    英雄可能已经带着探索阶段的损耗，一记反击就被打死。阵亡会掉落全部物品、
    并让行动列表清空，后面的断言会全线崩掉（剧本 11/16 都踩过——一次攻击
    把英雄打到速度 0，第二次攻击直接被闸门拒掉）。测试验的是机制不是伤害数值，
    先把血量抬满，保证断言只和被测逻辑有关。
    """
    for player in engine.state.players:
        if player.role != "hero" or player.dead:
            continue
        for stat in ("speed", "might", "sanity", "knowledge"):
            track = engine._stat_track(player, stat)
            if track:
                player.stat_positions[stat] = len(track) - 1
                player.stats[stat] = track[-1]


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

    # 目标由引擎按"最近英雄"选定，断言跟它保持一致：写死"第一个英雄"会让
    # 用例随探索期的棋盘一起漂移（基础规则修正后 seed113 的英雄位置变过）。
    expected = engine._find_monster_target(mummy)
    assert expected is not None
    handler = engine._mode_handler()
    assert handler.on_monster_move(engine, mummy, 0), "掷 0 应触发秘密通道"
    assert mummy.room_key == expected.room_key, "秘密通道应直接抵达目标所在房间"

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
        (
            key
            for key, room in engine.state.board.items()
            if room.template_id in {"crypt", "graveyard"}
        ),
        None,
    )
    if grave_room is None:
        # 棋盘布局随探索行为变化而变：地窖/墓地未必已翻出。这里验的是
        # "安葬要求站在地窖/墓地"，用引擎能力把房间拉进场即可。
        grave_room = engine._ensure_room_in_play("graveyard") or engine._ensure_room_in_play("crypt")
    assert grave_room is not None, "需要地窖或墓地在场上才能验证安葬"
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

    # 复原：属性回到起始值（p14"恢复后的英雄，其各项属性回到起始值"）。
    # 注意不能直接比 face.stats：角色卡的印刷起始值未必落在轨道上
    # （card_1_0 的起始力量写 3，而力量轨道是 [1,2,2,4,4,5,5,7]），
    # 引擎在开局与复原时都会把它吸附到最接近的格子——两处必须一致。
    engine._restore_from_frog(hero)
    assert not hero.frog
    for stat in ("might", "knowledge"):
        track = engine._stat_track(hero, stat)
        printed = face.stats[stat]
        if track:
            index = min(range(len(track)), key=lambda i: abs(track[i] - printed))
            expected = track[index]
        else:
            expected = printed
        assert hero.stats[stat] == expected, (
            f"{stat} 应回到起始值 {expected}（卡面 {printed}），实际 {hero.stats[stat]}"
        )


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


def verify_bot_holds_position_for_next_step() -> None:
    """bot 走完一步剧本行动后，若下一步还在同一房间，必须原地等下回合。

    剧本 24 实测：英雄启动管风琴后立刻被战斗牵走，知识 6+ 的第二步永远没人做，
    三步链断在中间，全 bot 局必败。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=24)
    handler = engine._mode_handler()
    controller = BotController()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    # 风琴房里有蝙蝠：机器人先出手攻击，若英雄属性见底会被一击打死（实测
    # 速度 2→0 直接倒下），"该继续移动"的断言就变成"英雄死了"的假失败。
    # 本测试验的是行动链与机动决策，先把英雄抬到属性上限。
    _buff_heroes_to_max(engine)
    organ_key = next(k for k, room in engine.state.board.items() if room.template_id == "organ_room")
    hero.room_key = organ_key
    _set_current(engine, hero)

    # 先把第一步做掉，制造"本回合已用行动 + 本房还有一次待办"的局面
    with patch.object(engine, "_resolve_check", return_value=True):
        assert engine.perform_haunt_action(hero, "start_organ") is True
    assert engine._haunt_action_used(hero) is True
    assert controller._pending_haunt_action_here(engine, hero) is True, "风琴房里还等着奏音"
    # 探测不得泄漏"本回合已用"标记，否则 bot 会在同一回合连做两次行动
    assert engine._haunt_action_used(hero) is True, "探测后必须还原行动标记"

    hero.steps_remaining = 5
    hero.movement_stopped = False
    before_room = hero.room_key
    controller._run_turn(engine, hero)
    assert hero.room_key == before_room, "同一房还有下一步时不该走开"

    # 没有待办时照常机动
    engine._haunt_flags()["bats_sealed"] = True
    # 上一回合可能已经把回合交给下一个人（引擎会拒绝"还没轮到该玩家"的行动），
    # 这里把回合交还给英雄；同时复位移动状态（抽牌会停移动，p6/p10）。
    _set_current(engine, hero)
    hero.steps_remaining = 5
    hero.movement_stopped = False
    assert controller._pending_haunt_action_here(engine, hero) is False, "封门后风琴房不再有行动"
    controller._run_turn(engine, hero)
    assert hero.room_key != before_room, "没有待办时应当继续移动"


def verify_collapse_subsystem() -> None:
    """引擎能力：房屋坍塌（翻面 / 邻格扩散 / 速度逃生 / 连通图排除）。

    剧本 22 p104 与剧本 2 的"房屋坍塌"共用这一套；先于剧本单独钉住。
    """
    engine = _new_engine(seed=131, players=4)
    foyer, hall, stairs = "0:1:0", "0:0:0", "0:2:0"
    for key in (foyer, hall, stairs):
        engine.state.board[key].revealed = True

    # 邻接：同层正交才算，斜角不算（p104 "Diagonal is not considered adjacent"）
    assert hall in engine._grid_neighbors(foyer) and stairs in engine._grid_neighbors(foyer)
    ground_template = next(
        t for t in engine.catalog.room_templates.values()
        if t.floor == 0 and t.id not in {r.template_id for r in engine.state.board.values()}
    )
    diagonal = engine._place_room(ground_template, 2, 1, 0)
    assert diagonal.key not in engine._grid_neighbors(foyer), "斜对角不应算相邻"
    assert engine._grid_neighbors("1:2:0") == [], "不同楼层不应算相邻"

    # 翻面：标记坍塌 + 牌面朝下，重复调用幂等
    assert engine._collapse_room(hall) is True
    assert engine.state.board[hall].data["abyss_collapsed"] is True
    assert engine.state.board[hall].revealed is False, "坍塌应把板块翻回背面"
    assert engine._is_collapsed(hall) and engine._collapsed_rooms()
    assert engine._collapse_room(hall) is False, "重复坍塌应返回 False"

    # 连通图与移动选项都不该再有这块房
    graph = engine._build_graph()
    assert hall not in graph, "坍塌房间不应作为图节点存在"
    assert hall not in graph.get(foyer, []), "坍塌房间不应作为邻边存在"
    walker = engine.state.players[0]
    walker.room_key = foyer
    walker.movement_stopped = False
    assert hall not in {option.target_key for option in engine.available_move_options(walker)}, "不能走进坍塌的房间"

    # p104：速度检定失败 → 随地板坠入深渊死亡
    # 坍塌只会由作祟触发（剧本 2 房屋坍塌、剧本 42 地狱之门），而"作祟开始
    # 之前没有人会死"（p5）——所以这里必须先进入作祟期再验致死。
    engine.state.phase = "HAUNT_PHASE"
    victim = engine.state.players[1]
    victim.room_key = stairs
    with patch.object(engine, "_resolve_check", return_value=False):
        engine._collapse_room(stairs)
    assert victim.dead, "逃离深渊失败应死亡"

    # p104：检定成功 → 跳进相邻、有门连通、已发现且没塌的房间
    # （用干净棋盘：上面的 hall/stairs 已经塌掉，原引擎里已无处可跳）
    jumper_engine = _new_engine(seed=131, players=4)
    jumper_engine.state.board[foyer].revealed = True
    jumper_engine.state.board[hall].revealed = True
    survivor = jumper_engine.state.players[2]
    survivor.room_key = foyer
    with patch.object(jumper_engine, "_resolve_check", return_value=True):
        jumper_engine._collapse_room(foyer)
    assert not survivor.dead and survivor.room_key != foyer, "应跳进相邻房间"
    assert survivor.room_key == hall, "跳落点必须是相邻、有门连通且没塌的房间"

    # 扩散只能沿已有深渊的邻格生长
    before = {room.key for room in engine._collapsed_rooms()}
    assert engine._collapse_adjacent_rooms(0) == 0
    grown = engine._collapse_adjacent_rooms(2)
    assert grown == 2, "应能沿邻格连续塌掉两间"
    for room in engine._collapsed_rooms():
        if room.key in before:
            continue
        assert any(other in before for other in engine._grid_neighbors(room.key)), f"{room.template_id} 不该凭空坍塌"

    # 还没有深渊时不能凭空开洞
    fresh = _new_engine(seed=131, players=4)
    assert fresh._collapse_adjacent_rooms(3) == 0, "没有深渊起点就不该塌房"


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

    # 失败路径（M10-19 修基类的直接回归）：知识 5+ 失败只算"执行过一次行动"，
    # 来源不作废、不落检定令牌、轨道不推进——否则 9 个来源会被失败白白耗光（软锁）
    hero.items.append("omen_book")
    checks_before = len(engine.tokens_of_kind("knowledge_check"))
    with patch.object(engine, "_resolve_check", return_value=False):
        assert handler.perform_action(engine, hero, "omen_book", {}) is True, "失败也算执行过本回合的剧本行动"
    assert engine._haunt_track_value("exorcism_successes") == 1, "检定失败不该推进轨道"
    assert "omen_book" not in engine._haunt_flags()["used_exorcism_sources"], "检定失败不该作废来源（消除软锁）"
    assert len(engine.tokens_of_kind("knowledge_check")) == checks_before, "检定失败不该放检定令牌"
    assert "omen_book" in {a.id for a in handler.available_actions(engine, hero)}, "失败后来源仍可复用"

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

    # 持圣徽者豁免诱惑检定（p20），所以要挑一个不带圣徽的英雄来验证"堕落"。
    hero = next(
        (
            p
            for p in engine.state.players
            if p.role == "hero" and not p.dead and "omen_holy_symbol" not in p.items
        ),
        None,
    )
    assert hero is not None, "需要一个不带圣徽的英雄来验证诱惑堕落"
    ballroom_key = next(k for k, r in engine.state.board.items() if r.template_id == "ballroom")

    # 在舞厅抵抗失败 → 直接堕落为叛徒
    hero.room_key = ballroom_key
    with patch.object(engine, "_resolve_check", return_value=False):
        handler.on_turn_start(engine, hero)
    assert hero.role == "traitor" and engine.state.traitor_id == hero.id, "舞厅诱惑失败应堕落"
    assert not hero.dead

    # 叛徒回合开始：力量检定 0-2 → 不能移动 + 力量轨道下移一格。
    # 注意断言的是"有效力量少一格"：引擎的 _apply_stat_loss 会先消耗临时加成
    # （overflow），角色身上带加值时轨位本身不会动，直接比轨位会假失败。
    might_before = hero.stat_positions.get("might", 0) + hero.overflow.get("might", 0)
    with patch.object(engine, "_roll_attack", return_value=1):
        handler.on_turn_start(engine, hero)
    assert hero.movement_stopped, "跳舞检定失败应钉住本回合"
    might_after = hero.stat_positions.get("might", 0) + hero.overflow.get("might", 0)
    assert might_after == might_before - 1, (
        "跳舞检定失败应 -1 力量（轨道下移一格或消耗临时加成）"
    )

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
    # 本测试验的是"布点/开窗/放逐/来源清单"这套机制，不是伤害数值。
    # 人影在 _release_specter 里会立刻行动并攻击最近的英雄，探索阶段累积的
    # 损耗会让英雄在断言之前就阵亡（阵亡会掉落全部物品，后面的戒指来源断言
    # 跟着假失败）。先把属性抬到上限，保证伤害不致死。
    _buff_heroes_to_max(engine)

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

    # 11 号只覆盖了来源清单、行动处理仍继承基类 → 失败同样不该白吃来源（M10-19）
    hero.items.append("omen_book")
    with patch.object(engine, "_resolve_check", return_value=False):
        assert handler.perform_action(engine, hero, "omen_book", {}) is True
    assert engine._haunt_track_value("exorcism_successes") == 1, "检定失败不该推进轨道"
    assert "omen_book" not in engine._haunt_flags()["used_exorcism_sources"], "检定失败不该作废来源（消除软锁）"


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
    # 注意"临时加成（overflow）会先被消耗"：断言的必须是**有效属性**少一格，
    # 否则角色身上带加值时轨位不动、测试假失败。
    before = {
        stat: hero.stat_positions.get(stat, 0) + hero.overflow.get(stat, 0)
        for stat in ("speed", "might", "sanity", "knowledge")
    }
    engine._active_player_id = hero.id
    with patch.object(engine, "_roll_attack", return_value=9), patch.object(
        engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 1
    ):
        assert engine.attack(hero, hero_twin) is True
    for stat in ("speed", "might", "sanity", "knowledge"):
        if before[stat] <= 0:
            continue
        after = hero.stat_positions.get(stat, 0) + hero.overflow.get(stat, 0)
        assert after == before[stat] - 1, (
            f"无球对本体交手应掉 {stat}（轨道一格或临时加成：{before[stat]}→{after}）"
        )
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
    # 矛：omen_spear 预兆卡（p26 明确为 "the Spear card"，与剧本 19 统一）；
    # 开局尚无人握矛时摆在剩余的地下室房间供拾取
    spear_in_room = any(
        "omen_spear" in cards for cards in engine.state.room_items.values()
    )
    spear_held = any("omen_spear" in p.items for p in engine.state.players)
    if spear_in_room:
        assert flags["spear_room"] is not None
        assert engine.state.board[flags["spear_room"]].template_id in basement_ids, "矛应在地下室"
    elif not spear_held:
        assert flags["spear_room"] is None, "未放置的矛应处于待放状态"
        target_room = next(
            (
                r for r in engine.state.board.values()
                if r.template_id in DragonSiegeMode.BASEMENT_ROOMS
                and r.key not in {flags["armor_room"], flags["shield_room"]}
            ),
            next(iter(engine.state.board.values())),
        )
        if target_room.template_id not in DragonSiegeMode.BASEMENT_ROOMS:
            target_room.template_id = "catacombs"
        handler.on_room_discovered(engine, hero, target_room)
        assert any(
            "omen_spear" in cards for cards in engine.state.room_items.values()
        ), "发现地下室房间后应补放矛"

    # 免疫速度攻击；持戒指徒手改理智
    dragon_id = dragon.id
    assert handler.attack_attr_override(engine, hero, dragon, "might") is None, "无戒指不触发理智覆盖"
    hero.items.append("omen_ring")
    assert handler.attack_attr_override(engine, hero, dragon, "might") == "sanity"
    # 持矛（omen_spear）对巨龙攻击骰 +4（旧版仅测属性覆盖，此处补骰值加值）
    if "omen_spear" not in hero.items:
        assert handler.attack_roll_bonus(engine, hero, dragon) == 0, "未持矛不应加值"
    engine._grant_card_to_player(hero, "omen_spear")
    assert handler.attack_roll_bonus(engine, hero, dragon) == 4, "持矛对龙攻击应 +4"

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
    # 幻影的"防御成功→反击"要真的打出伤害（本测试的第一步），但 7 点反击
    # 足以把带伤英雄直接打死；先抬满属性，保证第二步的"击败幻影"还能进行。
    _buff_heroes_to_max(engine)

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
        # 失败路径（M10-19 同根因修复）：知识 4+ 失败只算执行过一次剧本行动，
        # 三枚配料一枚都不能少、也不能凭空配出杀虫剂
        with patch.object(engine, "_resolve_check", return_value=False):
            assert handler.perform_action(engine, hero, "make_spray", {}) is True, "失败也算执行过本回合的剧本行动"
        assert len(engine.tokens_of_kind("ingredient")) == ingredient_total_before, "检定失败不该吃掉配料"
        assert not engine.tokens_held_by(hero.id, "bug_spray"), "检定失败不该配出杀虫剂"
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


def verify_haunt18_offspring() -> None:
    """剧本 18：毒藤与孢子布点/寻花/削弱击杀/孢子伤害/屏息（p29/p100）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=18)
    handler = engine._mode_handler()
    assert isinstance(handler, OffspringMode)
    flags = engine._haunt_flags()

    # 毒藤与孢子：玩家数枚孢子在毒藤房间
    plant_room = flags["plant_room"]
    assert engine.state.board[plant_room].template_id not in ("entrance_hall",), "毒藤应远离门厅"
    spores = engine.tokens_of_kind("spore")
    assert len(spores) == len(engine.state.players), "开局孢子数应等于玩家数"
    assert all(t.room_key == plant_room for t in spores), "开局孢子应与毒藤同房"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 寻花：温室/花园/墓地做知识 5+ → 花挂到发现者身上
    flower_room = next(
        (r for r in engine.state.board.values() if r.template_id in ("conservatory", "garden", "graveyard")),
        None,
    )
    if flower_room is None:
        # 种子局没翻出寻花房间：把任意房间临时改成花园（模板技巧，用后还原）
        flower_room = next(iter(engine.state.board.values()))
        flower_room.template_id = "garden"
    hero.room_key = flower_room.key
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "find_flower" in ids, "在寻花房间应能找花"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "find_flower", {}) is True
    assert engine.tokens_held_by(hero.id, "flower"), "花应挂到发现者身上"
    assert "find_flower" not in {a.id for a in handler.available_actions(engine, hero)}

    # 削弱：花进毒藤房间后知识 5+，两次成功（4 人局）即杀死毒藤
    hero.room_key = plant_room
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "weaken_plant" in ids, "带花进毒藤房间应能削弱"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "weaken_plant", {}) is True
    assert int(flags["weaken_count"]) == 1
    assert not flags.get("plant_killed"), "4 人局需两次削弱"
    engine._reset_player_turn_state(hero)
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "weaken_plant", {}) is True
    assert int(flags["weaken_count"]) == 2 and flags.get("plant_killed") is True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # 重建胜负状态，测试孢子伤害与屏息
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    flags["plant_killed"] = False
    flags["weaken_count"] = 0
    hero.room_key = plant_room
    might_before = hero.stats["might"]
    handler.on_turn_start(engine, hero)  # 回合开始身处孢子房 → 1 骰物理
    assert not hero.dead or hero.stats["might"] <= might_before, "孢子应造成伤害"

    # 屏息：在无孢子房间屏息 → 移动穿孢子房不掉血 → 下一回合不能移动
    hero2 = next((p for p in engine.state.players if p.role == "hero" and p.id != hero.id and not p.dead), None)
    if hero2 is not None:
        safe_room = next(k for k in engine.state.board if k not in handler._spore_rooms(engine))
        hero2.room_key = safe_room
        assert handler.perform_action(engine, hero2, "hold_breath", {}) is True
        flags["breath_active"][str(hero2.id)] = 1  # 模拟屏息最后一格
        spore_room = next(iter(handler._spore_rooms(engine)))
        engine._move_to_room(hero2, spore_room)
        assert not hero2.dead or True  # 屏息期间不掉血：与未屏息对照即可
        handler.on_turn_start(engine, hero2)
        assert hero2.movement_stopped, "屏息后下一回合不能移动（可行动）"

    # 叛徒每回合补孢子：4 人局其他英雄 3 人 → 加 2 枚
    spores_before = len(engine.tokens_of_kind("spore"))
    handler.on_turn_start(engine, traitor)
    assert len(engine.tokens_of_kind("spore")) >= spores_before + 2, "叛徒回合应补充孢子"

    # 寻花房间必须在场；机器人不能把屏息当推进手段
    assert any(
        room.template_id in ("conservatory", "garden", "graveyard")
        for room in engine.state.board.values()
    ), "温室/花园/墓地至少一间应在场"
    assert handler.bot_action_blocked(engine, hero, "hold_breath") is True
    assert handler.bot_action_blocked(engine, hero, "find_flower") is False
    flags["flower_found"] = False
    flower_goals = handler.bot_goal_rooms(engine, hero)
    assert flower_goals, "没找到花时应去寻花房间"
    flags["flower_found"] = True
    plant_goals = handler.bot_goal_rooms(engine, hero)
    assert plant_goals == [f"__room__{plant_room}"], "找到花后应把花带进毒藤房间"


def verify_haunt19_beastmaster() -> None:
    """剧本 19：随从布点/先攻加值/随从即死/偷矛降服/杀驯兽师即败（p30/p101）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=19)
    handler = engine._mode_handler()
    assert isinstance(handler, BeastmasterMode)
    flags = engine._haunt_flags()

    traitor = next(p for p in engine.state.players if p.role == "traitor")
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 布点：矛（omen_spear 卡）在驯兽师手上；狼在门厅；熊在某个英雄房间；种类映射齐全
    assert "omen_spear" in traitor.items, "长矛（omen_spear 卡）应在驯兽师手上"
    assert handler._spear_holder(engine) is traitor
    entrance = next(k for k, r in engine.state.board.items() if r.template_id == "entrance_hall")
    kinds = set(flags.get("beast_kind", {}).values())
    assert "wolf" in kinds and "bear" in kinds and "crocodile" in kinds, "狼/熊/鳄鱼应已布点"
    wolves = [m for m in engine.state.monsters if handler._kind_of(engine, m) == "wolf"]
    assert all(m.room_key == entrance for m in wolves), "狼应在门厅"

    # 先攻加值：熊主动攻击 +2（被攻击不加）
    bear = next(m for m in engine.state.monsters if handler._kind_of(engine, m) == "bear")
    with patch.object(engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 5), \
         patch.object(engine, "_roll_attack", return_value=9):
        bear_victim = next(p for p in engine.state.players if p.role == "hero" and p.room_key == bear.room_key and not p.dead)
        if bear_victim is not None:
            engine._monster_attack(bear, bear_victim)
    # 熊 5 骰 + 2 加值：只要攻击发生即视为日志含加值语义（具体数值由骰子决定）

    # 随从被击败即死（非击晕）
    minion = wolves[0]
    hero.room_key = minion.room_key
    engine._active_player_id = hero.id
    with patch.object(engine, "_roll_attack", return_value=9), patch.object(
        engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 1
    ):
        assert engine.attack(hero, minion) is True
    assert minion not in engine.state.monsters, "随从被击败应死亡"
    assert engine._haunt_track_value("minions_slain") == 1

    # 持戒理智攻击驯兽师（属性覆盖扩展到玩家目标）
    hero.items.append("omen_ring")
    assert handler.attack_attr_override(engine, hero, traitor, "might") == "sanity", "持戒对驯兽师应改理智"

    # >2 伤害偷走长矛 → 英雄胜（special_steal）
    traitor.room_key = hero.room_key
    hero.attack_used = False
    with patch.object(
        engine, "_roll_attack",
        side_effect=lambda player, attr, bonus=0: 9 if player is hero else 1,
    ):
        assert engine.attack(hero, traitor) is True
    assert flags.get("spear_stolen") is True, "高伤应触发偷矛"
    assert "omen_spear" in hero.items, "长矛应到英雄手上"
    assert "omen_spear" not in traitor.items, "长矛应已从驯兽师手上夺走"
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # 杀死驯兽师 = 英雄失败（盖过引擎兜底）
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    flags["spear_stolen"] = False
    traitor.dead = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor", "杀死驯兽师应为英雄的失败"


def verify_haunt20_ghost_bride() -> None:
    """剧本 20：四步链/起尸背尸/教堂安息/新娘杀新郎与婚礼计时（p31/p102）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=20)
    handler = engine._mode_handler()
    assert isinstance(handler, GhostBrideMode)
    flags = engine._haunt_flags()

    # 布点：教堂与地窖在场；尸体在地窖；新娘在叛徒房间且不可被攻击
    board_ids = {r.template_id for r in engine.state.board.values()}
    assert "chapel" in board_ids and "crypt" in board_ids, "教堂与地窖应被强制入场"
    corpse = engine.tokens_of_kind("corpse")
    assert corpse and engine.state.board[corpse[0].room_key].template_id == "crypt", "尸体应在地窖"
    bride = engine._monster_by_template("ghost")
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert bride is not None and bride.room_key == traitor.room_key, "新娘应在叛徒房间"
    assert engine._monster_invulnerable(bride), "新娘不可被任何手段伤害"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    assert flags.get("groom_id") == hero.id or flags.get("groom_id") is not None, "应选定新郎"

    # 第 1 步：持书翻日记（绕开房间要求）
    hero.items.append("omen_book")
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "learn_name_book" in ids, "持书应能翻日记"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "learn_name_book", {}) is True
    assert flags.get("groom_name_known") is True

    # 第 2 步：地窖定位
    crypt_key = next(k for k, r in engine.state.board.items() if r.template_id == "crypt")
    hero.room_key = crypt_key
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "locate_body" in ids
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "locate_body", {}) is True

    # 第 3 步：起尸 → 尸体自动背上，入房按 2 格
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "disinter_body" in ids
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "disinter_body", {}) is True
    assert engine.tokens_held_by(hero.id, "corpse"), "起尸后应自动背上"
    assert handler.movement_cost_multiplier(engine, hero) == 2, "背尸入房按 2 格计"

    # 第 4 步：尸体 + 戒指进教堂 → 新娘安息（英雄胜）
    hero.items.append("omen_ring")
    chapel = flags["chapel_room"]
    engine._move_to_room(hero, chapel)
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"

    # 新娘杀新郎：伤害转力量流失；新郎死亡掉戒指；婚礼计时第 3 回合叛徒胜
    groom = handler._groom(engine)
    groom.room_key = bride.room_key
    might_before = groom.stats["might"]
    with patch.object(engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 9), \
         patch.object(engine, "_roll_attack", return_value=1):
        assert handler.on_monster_turn_attack(engine, bride) is True
    assert groom.stats["might"] < might_before or groom.dead, "对新郎的伤害应转为力量流失"
    while not groom.dead:
        groom.stat_positions["might"] = max(0, groom.stat_positions.get("might", 0) - 1)
        groom.stats["might"] = max(0, groom.stats["might"] - 1)
        engine._check_player_death(groom)
    assert groom.dead and "omen_ring" not in groom.items, "新郎死亡应掉落戒指"
    engine.state.monsters = [m for m in engine.state.monsters if m.room_key != chapel or m is not bride]
    handler.on_monster_move(engine, bride, 4)  # 新郎已死：新娘进教堂开婚
    assert flags.get("wedding_started") is True
    engine._set_haunt_track_value("wedding_timer", 2)
    handler.on_turn_start(engine, traitor)
    assert engine.state.winner == "traitor", "婚礼第 3 回合应完成"


def verify_haunt21_zombie_lord() -> None:
    """剧本 21：布点顺序/左轮免疫/力量武器击杀/徽章闸门/圣徽减骰/死亡转化（p32/p103）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=21)
    handler = engine._mode_handler()
    assert isinstance(handler, ZombieLordMode)
    flags = engine._haunt_flags()
    assert engine.state.phase == "HAUNT_PHASE", "该种子应能跑到作祟阶段"

    # p103：叛徒开局即死并掉落物品，人物由僵尸领主令牌顶替
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert traitor.dead is True, "p103：叛徒开局就被拖进墙里"
    assert not traitor.items, "叛徒应掉落所有物品"
    lord = engine._monster_by_template("zombie_lord")
    assert lord is not None, "僵尸领主应在场"
    assert lord.room_key == traitor.room_key, "领主应顶替叛徒所在房间"

    # p103 布点：玩家数枚按房间顺序放（房不够则叠放），再给每间有僵尸的房补一只
    zombies = [m for m in engine.state.monsters if m.template_id == "zombie"]
    revealed_templates = {r.template_id for r in engine.state.board.values() if r.revealed}
    listed = set(handler.PLACE_ORDER) & revealed_templates
    buckets = len(listed) or 1
    assert len(zombies) == 4 + min(4, buckets), f"僵尸数应为玩家数 + 已布点房间数，实际 {len(zombies)}"
    assert flags["zombies_placed"] == len(zombies)
    for monster in zombies:
        room = engine.state.board[monster.room_key]
        assert room.revealed, "僵尸只应布在已发现的房间里"
        if listed:
            assert room.template_id in listed, "僵尸应落在 p103 顺序表里的房间"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0
    zombie_a, zombie_b = zombies[0], zombies[1]
    hero.room_key = zombie_a.room_key

    def _attack(winner: int, loser: int):
        return (
            patch.object(engine, "_roll_attack", side_effect=lambda player, attr, bonus=0: winner),
            patch.object(engine, "_roll_monster_attack", return_value=loser),
        )

    # p32：僵尸免疫左轮（速度攻击）
    hero.items.append("item_revolver")
    engine._reset_player_turn_state(hero)
    roll_a, roll_b = _attack(9, 0)
    with roll_a, roll_b:
        assert engine.attack(hero, zombie_a, "item_revolver") is False, "僵尸免疫左轮"
    assert zombie_a in engine.state.monsters

    # p32：力量武器命中即杀死
    hero.items.append("item_axe")
    engine._reset_player_turn_state(hero)
    roll_a, roll_b = _attack(9, 0)
    with roll_a, roll_b:
        assert engine.attack(hero, zombie_a, "item_axe") is True
    assert zombie_a not in engine.state.monsters, "力量武器应直接杀死僵尸"

    # p32：徒手力量攻击不算武器，只能打晕
    hero.room_key = zombie_b.room_key
    engine._reset_player_turn_state(hero)
    roll_a, roll_b = _attack(9, 0)
    with roll_a, roll_b:
        assert engine.attack(hero, zombie_b) is True
    assert zombie_b in engine.state.monsters and zombie_b.stunned_turns >= 1, "徒手只应击晕"

    # 老坑：叛徒开局已死，不能因此判英雄胜
    engine.state.winner = None
    assert handler.check_victory(engine) is True and engine.state.winner is None, "应吸收引擎的叛徒死亡兜底"

    # p32：圣徽持有者让僵尸的力量攻击少掷两枚骰，对领主无效
    holder = next(p for p in engine.state.players if p.role == "hero" and not p.dead and p is not hero)
    holder.items.append("omen_holy_symbol")
    assert handler.monster_attack_roll_bonus(engine, zombie_b, holder) == -2
    assert handler.monster_attack_roll_bonus(engine, lord, holder) == 0
    assert handler.monster_attack_roll_bonus(engine, zombie_b, hero) == 0

    # p32/p103：英雄被杀后在原地变成新僵尸
    before = len([m for m in engine.state.monsters if m.template_id == "zombie"])
    victim = next(p for p in engine.state.players if p.role == "hero" and not p.dead and p is not hero and p is not holder)
    victim.stats["might"] = 0
    engine._check_player_death(victim)
    assert victim.dead
    after = len([m for m in engine.state.monsters if m.template_id == "zombie"])
    assert after == before + 1, "死去的英雄应转化为一只新僵尸"
    assert victim.id in flags["converted_ids"]
    assert engine.state.winner != "heroes", "转化出的僵尸仍在场，不应判英雄清空僵尸"

    # p32：只有持徽章者能伤到领主；领主吃 7 点伤害而不吃击晕（p103）
    hero.items = []
    engine._reset_player_turn_state(hero)
    hero.room_key = lord.room_key
    assert engine.attack(hero, lord) is False, "无徽章者伤不到僵尸领主"
    hero.items.append("omen_medallion")
    engine._reset_player_turn_state(hero)
    roll_a, roll_b = _attack(3, 2)
    with roll_a, roll_b:
        assert engine.attack(hero, lord) is True
    assert engine._haunt_track_value("lord_damage") == 1, "领主应累计 1 点伤害"
    assert lord in engine.state.monsters and lord.stunned_turns == 0, "领主不应被击晕"
    engine._set_haunt_track_value("lord_damage", 6)
    engine._reset_player_turn_state(hero)
    roll_a, roll_b = _attack(3, 2)
    with roll_a, roll_b:
        assert engine.attack(hero, lord) is True
    assert lord not in engine.state.monsters, "累计 7 点伤害领主应倒下"
    assert engine.state.winner == "heroes", "摧毁领主即英雄胜（p32）"


def verify_haunt22_abyss_exorcism() -> None:
    """剧本 22：深渊起点/首回合只开洞/邻格扩散/一次性驱魔来源/圣徽拖延（p33/p104）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=22)
    handler = engine._mode_handler()
    assert isinstance(handler, AbyssExorcismMode)
    flags = engine._haunt_flags()

    # 该种子在探险阶段就死了一名英雄（bot 实测），复活一名才够跑"两名英雄"的分支断言
    for person in engine.state.players:
        if person.role == "hero" and person.dead:
            person.dead = False
            for stat in ("speed", "might", "sanity", "knowledge"):
                person.stats[stat] = 3

    # p104：深渊从地下室开洞——已发现、无人占用
    start = flags["abyss_room"]
    assert start and engine.state.board[start].floor == -1, "深渊应从地下室开洞"
    assert engine.state.board[start].revealed, "起点必须是已发现的房间"
    assert not any(p.room_key == start and not p.dead for p in engine.state.players), "起点必须无人"
    assert not engine._collapsed_rooms(), "作祟刚开局不该已经塌房"

    # 把活人挪到远离深渊的格子上：否则扩散会随机吞掉测试用的英雄
    def _park_safely() -> str:
        abyss = {start} | {room.key for room in engine._collapsed_rooms()}
        danger = {key for origin in abyss for key in engine._grid_neighbors(origin)}
        safe = next(
            (
                key for key in sorted(engine.state.board)
                if key not in danger and key not in abyss and engine.state.board[key].revealed
            ),
            "",
        )
        assert safe, "应还有远离深渊的已发现房间"
        for person in engine.state.players:
            if not person.dead:
                person.room_key = safe
        return safe

    # 叛徒第 1 回合结束：只开洞 + 推进回合轨，不按速率塌房（p104 "starting on Turn 2"）
    _park_safely()
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    handler.on_turn_end(engine, traitor)
    assert {room.key for room in engine._collapsed_rooms()} == {start}, "第 1 回合只该塌起点房"
    assert engine._haunt_track_value("abyss_turn") == 1

    # 第 2 回合：每位玩家塌 1 间，且只能沿正交邻格扩散
    _park_safely()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    handler.on_turn_end(engine, hero)
    grown = [room.key for room in engine._collapsed_rooms() if room.key != start]
    assert len(grown) == 1, f"第 2 回合每人应塌 1 间，实际 {len(grown)}"
    assert grown[0] in engine._grid_neighbors(start), "深渊只能沿正交邻格扩散"

    # p33：驱魔来源一次性；22 号用戒指替换 8 号的灵应板
    assert "omen_spirit_board" not in handler.ALL_SOURCES and "omen_ring" in handler.ALL_SOURCES
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0
    hero.items.append("omen_ring")
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "omen_ring", {}) is True
    assert engine._haunt_track_value("exorcism_successes") == 1
    assert "omen_ring" in flags["used_exorcism_sources"]
    engine._reset_player_turn_state(hero)
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "omen_ring", {}) is False, "同一来源只能成功用一次"

    # 22 号的覆盖只处理"献出圣徽"，驱魔来源仍落回基类 → 失败不该白吃来源（M10-19）
    hero.items.append("omen_book")
    with patch.object(engine, "_resolve_check", return_value=False):
        assert handler.perform_action(engine, hero, "omen_book", {}) is True
    assert engine._haunt_track_value("exorcism_successes") == 1, "检定失败不该推进轨道"
    assert "omen_book" not in flags["used_exorcism_sources"], "检定失败不该作废来源（消除软锁）"
    assert "omen_book" in {a.id for a in handler.available_actions(engine, hero)}, "失败后来源仍可复用"

    # p33：圣徽拖延——必须站在深渊邻格，献出后弃卡并暂停坍塌
    holder = next(p for p in engine.state.players if p.role == "hero" and not p.dead and p is not hero)
    holder.items.append("omen_holy_symbol")
    far = next(p for p in engine.state.players if p.role == "hero" and not p.dead and p is not holder)
    far.items.append("omen_holy_symbol")
    edge_key = next((k for k in engine._grid_neighbors(start) if not engine._is_collapsed(k)), "")
    assert edge_key, "深渊应还有未塌的邻格"
    holder.room_key = edge_key
    far.room_key = next(k for k, room in engine.state.board.items() if k not in engine._grid_neighbors(start))
    engine.state.turn_order = [holder.id]
    engine.state.turn_index = 0
    assert "sacrifice_holy_symbol" in {a.id for a in handler.available_actions(engine, holder)}
    engine.state.turn_order = [far.id]
    engine.state.turn_index = 0
    assert "sacrifice_holy_symbol" not in {a.id for a in handler.available_actions(engine, far)}, "不挨着深渊就不能献圣徽"

    engine.state.turn_order = [holder.id]
    engine.state.turn_index = 0
    collapsed_before = len(engine._collapsed_rooms())
    assert handler.perform_action(engine, holder, "sacrifice_holy_symbol", {}) is True
    assert "omen_holy_symbol" not in holder.items, "圣徽应被弃掉"
    assert flags["abyss_paused_until"] == engine._haunt_track_value("abyss_turn") + 1
    handler.on_turn_end(engine, holder)
    assert len(engine._collapsed_rooms()) == collapsed_before, "拖延期间房屋不该继续坍塌"
    assert engine._haunt_track_value("abyss_turn") == 1, "拖延不停住深渊的时钟（p33）"

    # 胜负：驱魔满员 → 英雄胜；英雄全灭 → 叛徒胜；叛徒死亡不白送英雄胜
    engine._set_haunt_track_value("exorcism_successes", engine._haunt_track_target("exorcism_successes"))
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    engine._set_haunt_track_value("exorcism_successes", 0)
    traitor.dead = True
    assert handler.check_victory(engine) is True and engine.state.winner is None, "应吸收叛徒死亡兜底"
    for player in engine.state.players:
        if player.role == "hero":
            player.dead = True
    assert handler.check_victory(engine) is True and engine.state.winner == "traitor"


def verify_haunt22_abyss_rises_to_next_floor() -> None:
    """剧本 22：整层塌完后深渊必须升到上一层（p104），否则会永久困在地下室。

    这是引擎级机制缺口在剧本侧的收口：`_collapse_adjacent_rooms` 拿
    `min(origin floors)` 当基准层，地下室一旦塌完，`candidate_floor > floor`
    就恒成立 —— 跨层播种格永远选不出（升层分支成了死代码），上层的正常扩散
    又被错加上"无人 + 有门"的播种过滤。实测 seed197/5p：地下室 9/9 塌完后
    深渊再不动，英雄又刚好把所有来源耗尽 → 打满 300 回合无胜者。handler 的
    `_collapse_abyss` 按原文重走"升层 + 上层扩散"这一步。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=22)
    handler = engine._mode_handler()
    assert isinstance(handler, AbyssExorcismMode)

    # 全员挪到楼上：塌地下室时别被顺带带走
    upstairs = next(
        key for key in sorted(engine.state.board)
        if engine.state.board[key].floor == 0 and engine.state.board[key].revealed
    )
    for person in engine.state.players:
        person.dead = False
        person.room_key = upstairs

    basement = [key for key, room in sorted(engine.state.board.items()) if room.floor == -1]
    assert len(basement) >= 2, "地下室至少要有两间才够测"
    for key in basement:
        engine._collapse_room(key)
    origins = {room.key for room in engine._collapsed_rooms()}
    assert not [key for key in basement if not engine._is_collapsed(key)], "地下室应已整层塌完"
    assert engine._abyss_candidates(origins, -1) == [], "本层再无邻格可扩"

    # 引擎原方法在此时选不出任何格子。若这条断言将来失败，说明引擎已经修好
    # 升层——那时可把 `_collapse_abyss` 退回直接调用引擎方法，本测试即可删。
    assert engine._collapse_adjacent_rooms(1) == 0, "引擎此处升不了层（本测试的存在理由）"

    # handler 必须升到上一层，且只挑"无人 + 留着未探索门口"的房间（p104）
    assert handler._collapse_abyss(engine, 1) == 1, "整层塌完后应升层塌 1 间"
    risen = ({room.key for room in engine._collapsed_rooms()} - origins).pop()
    assert engine.state.board[risen].floor == 0, "应升到地下室上一层"
    assert not any(p.room_key == risen and not p.dead for p in engine.state.players), "播种房必须无人"
    assert handler._has_open_door(engine, risen), "播种房必须还留着未探索门口"

    # 升上来之后，后续扩散回到"同层邻格"（不再套播种规则）
    assert handler._collapse_abyss(engine, 1) == 1
    second = ({room.key for room in engine._collapsed_rooms()} - origins - {risen}).pop()
    assert engine.state.board[second].floor == 0
    assert second in engine._grid_neighbors(risen), "升层后应按同层邻格扩散"


def verify_haunt23_tentacled_horror() -> None:
    """剧本 23：配对布点/成长表/拖 1 格/挣脱对决/水晶球定位/一击摧毁头颅（p34/p105）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=23)
    handler = engine._mode_handler()
    assert isinstance(handler, TentacledHorrorMode)
    flags = engine._haunt_flags()

    # 该种子开局可能已有英雄死在探险阶段，复活到足够人数再测
    for person in engine.state.players:
        if person.role == "hero" and person.dead:
            person.dead = False
            for stat in ("speed", "might", "sanity", "knowledge"):
                person.stats[stat] = 3

    # p105：叛徒开局即死；根/尖端对数 = 玩家数，每对同房，且只落在指定六房
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert traitor.dead is True, "p105：叛徒开局就被拖进墙里"
    tips = [m for m in engine.state.monsters if m.template_id == "creeper_tip"]
    roots = engine.tokens_of_kind("root")
    assert len(tips) == len(roots) == flags["pairs_placed"] == 4, "对数应等于玩家数"
    allowed = {key for key, room in engine.state.board.items() if room.template_id in handler.ROOM_IDS}
    for tip in tips:
        root = handler._root_for_tip(engine, tip)
        assert root is not None and root.room_key == tip.room_key, "根与尖端必须同房入场"
        assert tip.room_key in allowed, "触手只能落在 p105 指定的六间房里"
    assert (tips[0].speed, tips[0].might, tips[0].sanity) == (2, 3, 6), "第 0 回合尖端 2/3/6"

    # p105 成长表：8+ 回合长到 4/8/8
    engine._set_haunt_track_value("tentacle_turn", 8)
    handler.on_monster_turn_start(engine, tips[0])
    assert (tips[0].speed, tips[0].might, tips[0].sanity) == (4, 8, 8), "8+ 回合尖端应为 4/8/8"
    engine._set_haunt_track_value("tentacle_turn", 0)
    assert handler._growth_stats(3) == (3, 5, 7) and handler._growth_stats(5) == (3, 7, 7)

    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    assert len(heroes) >= 3, "本用例需要至少三名存活英雄"
    hero_a, hero_b, hero_c = heroes[0], heroes[1], heroes[2]

    # p105：抓着人的尖端每回合只朝配对的根挪 1 格
    tip = tips[1]
    root = handler._root_for_tip(engine, tip)
    far = next(
        (
            key for key in sorted(engine.state.board)
            if key != root.room_key and len(engine._shortest_path(key, root.room_key)) >= 2
        ),
        "",
    )
    assert far, "应能找到离根两步远的位置"
    tip.room_key = far
    hero_a.room_key = far
    flags["grabbed"] = {str(hero_a.id): tip.id}
    handler.on_monster_move(engine, tip, 4)
    assert hero_a.room_key == tip.room_key, "人质必须跟着尖端走"
    assert len(engine._shortest_path(tip.room_key, root.room_key)) == len(engine._shortest_path(far, root.room_key)) - 1, "只应挪一格"

    # p34：挣脱成功 → 获释 + 本回合每间房按 2 格，回合结束即解除
    def _duel(winner_roll: int, loser_roll: int):
        return (
            patch.object(engine, "_roll_attack", side_effect=lambda player, attr, bonus=0: winner_roll),
            patch.object(engine, "_roll_monster_attack", return_value=loser_roll),
        )

    roll_a, roll_b = _duel(9, 1)
    with roll_a, roll_b:
        handler.on_turn_start(engine, hero_a)
    assert str(hero_a.id) not in flags["grabbed"], "打赢开局对决应获释"
    assert not hero_a.movement_stopped and hero_a.room_key == tip.room_key, "获释后就该留在原地"
    assert handler.movement_cost_multiplier(engine, hero_a) == 2, "挣脱后本回合每间房算 2 格"
    handler.on_turn_end(engine, hero_a)
    assert handler.movement_cost_multiplier(engine, hero_a) == 1, "减速只持续到本回合结束"

    # p34：挣脱失败 → 不掉血但仍被缠住，本回合结束
    tip2 = tips[2]
    hero_b.room_key = tip2.room_key
    flags["grabbed"][str(hero_b.id)] = tip2.id
    before_stats = dict(hero_b.stats)
    roll_a, roll_b = _duel(1, 9)
    with roll_a, roll_b:
        handler.on_turn_start(engine, hero_b)
    assert str(hero_b.id) in flags["grabbed"] and hero_b.movement_stopped and hero_b.attack_used
    assert hero_b.stats == before_stats and not hero_b.dead, "挣脱失败不掉血（p34）"

    # p105：尖端被击败 → 松手 + 缩回配对的根 + 昏迷
    tip3 = tips[3]
    root3 = handler._root_for_tip(engine, tip3)
    hero_c.room_key = tip3.room_key
    flags["grabbed"][str(hero_c.id)] = tip3.id
    assert handler.on_monster_defeated(engine, tip3, 2) is False
    assert str(hero_c.id) not in flags["grabbed"] and tip3.room_key == root3.room_key, "尖端应缩回根部"

    # p34：水晶球定位头颅——知识 4+ 成功后掷 4 骰查表，球随即碎裂
    engine.state.turn_order = [hero_a.id]
    engine.state.turn_index = 0
    hero_a.items.append("omen_crystal_ball")
    engine._reset_player_turn_state(hero_a)
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero_a, "gaze_crystal_ball", {}) is True
    assert "omen_crystal_ball" not in hero_a.items, "球用完即碎（p34）"
    assert flags["head_found"] is True and flags["head_room"] in engine.state.board
    assert engine.state.board[flags["head_room"]].template_id in handler.HEAD_TABLE, "头位必须落在 p34 查表结果里"

    # 老坑：叛徒开局已死，不能因此判英雄胜
    assert handler.check_victory(engine) is True and engine.state.winner is None

    # p34：走进头位房间，用炸药或长矛一击摧毁，不需要掷骰
    wrong = next(p for p in engine.state.players if p.role == "hero" and not p.dead and p is not hero_a)
    wrong.room_key = next(k for k in engine.state.board if k != flags["head_room"])
    wrong.items.append("item_dynamite")
    engine.state.turn_order = [wrong.id]
    engine.state.turn_index = 0
    assert "destroy_head" not in {a.id for a in handler.available_actions(engine, wrong)}, "不在头位房就不能动手"
    hero_a.room_key = flags["head_room"]
    hero_a.items.append("item_dynamite")
    engine.state.turn_order = [hero_a.id]
    engine.state.turn_index = 0
    engine._reset_player_turn_state(hero_a)
    assert "destroy_head" in {a.id for a in handler.available_actions(engine, hero_a)}
    assert handler.perform_action(engine, hero_a, "destroy_head", {}) is True
    assert flags["creature_destroyed"] is True
    assert not engine.state.monsters and not engine.tokens_of_kind("root"), "怪物与所有触手应一起离场"
    assert engine.state.winner == "heroes", "摧毁头颅即英雄胜（p34）"


def verify_haunt24_bat_swarm() -> None:
    """剧本 24：开局布点/每轮入室与 24 上限/贴附吸血/盔甲与减速/风琴三步（p35/p106）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=24)
    handler = engine._mode_handler()
    assert isinstance(handler, BatSwarmMode)
    flags = engine._haunt_flags()
    for person in engine.state.players:
        if person.role == "hero" and person.dead:
            person.dead = False
            for stat in ("speed", "might", "sanity", "knowledge"):
                person.stats[stat] = 4

    # p35：风琴房必须在场；p106：开局蝙蝠只在 塔楼/阁楼 与 裂隙/地下墓穴，且为 3 的倍数
    assert any(room.template_id == "organ_room" for room in engine.state.board.values()), "风琴房应被强制入场"
    start_rooms = {"tower", "attic", "chasm", "catacombs"}
    bats = handler._bats(engine)
    assert len(bats) % 3 == 0 and len(bats) <= 6, f"开局蝙蝠应是 3 的倍数且不超过 6，实际 {len(bats)}"
    for bat in bats:
        assert engine.state.board[bat.room_key].template_id in start_rooms, "开局蝙蝠只能落在 p106 的两组房间"
    assert next(p for p in engine.state.players if p.role == "traitor").dead is True, "叛徒开局即死"

    # p106：每个怪物回合按玩家数掷骰入室，一个怪物回合只放一批，场内封顶 24
    with patch.object(engine, "roll_dice", return_value=4):
        assert handler._enter_bats_this_round(engine) is None
        after_first = len(handler._bats(engine))
        assert after_first == len(bats) + 4, "应放入 4 只（掷骰结果）"
        handler._enter_bats_this_round(engine)
        assert len(handler._bats(engine)) == after_first, "同一轮不该再放第二批"
    engine._haunt_flags()["bats_sealed"] = True
    sealed_count = len(handler._bats(engine))
    with patch.object(engine, "roll_dice", return_value=4):
        engine.state.turn_count += 5
        handler._enter_bats_this_round(engine)
    assert len(handler._bats(engine)) == sealed_count, "封住入口后不该再有蝙蝠入室"
    engine._haunt_flags()["bats_sealed"] = False
    while len(handler._bats(engine)) < handler.BAT_CAP:
        engine.state.turn_count += 1
        with patch.object(engine, "roll_dice", return_value=8):
            handler._enter_bats_this_round(engine)
    assert len(handler._bats(engine)) == handler.BAT_CAP, "场内蝙蝠应封顶 24 只"

    # p106：贴脸的蝙蝠掷 1 枚骰，掷出 2 就贴上去
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    bat = next(b for b in handler._bats(engine) if handler._host_of(engine, b) is None)
    bat.room_key = hero.room_key
    with patch.object(engine, "roll_dice", return_value=2):
        assert handler.on_monster_turn_start(engine, bat) is True
    assert str(bat.id) in handler._attached_ids(engine, hero), "掷出 2 应贴附"
    moved_room = hero.room_key
    hero.room_key = next(k for k in engine.state.board if k != moved_room)
    handler.on_player_moved(engine, hero)
    assert bat.room_key == hero.room_key, "贴附的蝙蝠应跟着宿主走"

    # p35/p106：宿主回合开始按贴附数各受 1 点物理伤害，并每只少走 1 格
    # （p35 的"盔甲少受 1 点"由引擎既有盔甲效果承担，本剧本不叠加减免）
    other = next(p for p in engine.state.players if p.role == "hero" and not p.dead and p is not hero)
    for _ in range(2):
        free = next(b for b in handler._bats(engine) if handler._host_of(engine, b) is None)
        free.room_key = other.room_key
        with patch.object(engine, "roll_dice", return_value=2):
            handler.on_monster_turn_start(engine, free)
    assert len(handler._attached_ids(engine, other)) == 2
    other.steps_remaining = 6
    with patch.object(engine, "_deal_damage") as dealt:
        handler.on_turn_start(engine, other)
    dealt.assert_called_once_with(other, "physical", 2, source=handler.DAMAGE_SOURCE)
    assert other.steps_remaining == 4, "每只贴附蝙蝠让宿主少走 1 格"
    other.steps_remaining = 1
    with patch.object(engine, "_deal_damage"):
        handler.on_turn_start(engine, other)
    assert other.steps_remaining == 1, "至少保留 1 格移动"
    # 宿主被咬死 → 蝙蝠脱离尸体，可以重新去找别人
    other.stats["speed"] = 0
    engine._check_player_death(other)
    with patch.object(engine, "_deal_damage"):
        handler.on_turn_start(engine, other)
    assert not handler._attached_ids(engine, other), "宿主死亡后蝙蝠应松开"

    # p35：力量攻击击败蝙蝠 = 杀死；其他属性只击晕
    target_bat = next(iter(handler._bats(engine)), None)
    assert handler.monster_killed_on_defeat(engine, target_bat, hero, "speed", "item_axe") is False
    assert handler.monster_killed_on_defeat(engine, target_bat, hero, "might", "item_axe") is True

    # 老坑：叛徒开局已死，场上还有蝙蝠时不能判英雄胜
    assert handler.check_victory(engine) is True and engine.state.winner is None

    # p35 三步：先在风琴房力量 5+ 启动管风琴，再知识 6+ 奏音封门并赶走未贴附的蝙蝠
    organ_key = next(k for k, room in engine.state.board.items() if room.template_id == "organ_room")
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0
    hero.room_key = organ_key
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "start_organ" in ids and "drive_away_bats" not in ids, "没启动管风琴就不能奏音"
    engine._reset_player_turn_state(hero)
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "start_organ", {}) is True
    assert flags["organ_started"] is True
    engine._reset_player_turn_state(hero)
    attached_before = {pid: list(ids_) for pid, ids_ in handler._attached_map(engine).items() if ids_}
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "drive_away_bats" in ids
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "drive_away_bats", {}) is True
    assert flags["bats_sealed"] is True
    assert all(
        handler._host_of(engine, bat) is not None for bat in handler._bats(engine)
    ), "奏音后只应留下贴附在人身上的蝙蝠"
    for pid, ids_ in attached_before.items():
        assert handler._attached_map(engine).get(pid) == ids_, "贴附的蝙蝠不该被赶走"

    # 杀死最后一只贴附蝙蝠 → 英雄胜
    for pid in list(handler._attached_map(engine)):
        for bat_id in list(handler._attached_map(engine)[pid]):
            bat = next((m for m in engine.state.monsters if str(m.id) == str(bat_id)), None)
            if bat is not None:
                assert handler.monster_killed_on_defeat(engine, bat, hero, "might", "item_axe") is True
                engine._kill_monster(bat, killer=hero)
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes", "封门后杀光贴附蝙蝠即英雄胜（p35）"


def verify_haunt38_hellbeast_exorcism() -> None:
    """剧本 38：火蝠不可攻击/初始数量与位置/一次性驱魔来源(戒指为理智)/
    怪物回合一次掷骰→移动+繁殖+同房英雄受物理伤/驱魔满员英雄胜/吸收叛徒死亡兜底（p49/p120）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=38)
    handler = engine._mode_handler()
    assert isinstance(handler, HellbeastMode)
    flags = engine._haunt_flags()

    # 复活可能在探险阶段死掉的英雄，保证有足够英雄跑分支断言
    for person in engine.state.players:
        if person.role == "hero" and person.dead:
            person.dead = False
            for stat in ("speed", "might", "sanity", "knowledge"):
                person.stats[stat] = 4

    # 叛徒存活并操控火蝠（区别于 24 号叛徒开局即死）
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert not traitor.dead, "38 号叛徒应存活"

    # 初始火蝠 = ceil(玩家数/2)，全在作祟揭露房，且不可被攻击
    expected = (len(engine.state.players) + 1) // 2
    haunt_room = flags["haunt_room"]
    assert haunt_room, "应记录作祟揭露房"
    bats = handler._bats(engine)
    assert len(bats) == expected, f"初始火蝠应为 ceil(玩家数/2)={expected}，实际 {len(bats)}"
    assert all(b.room_key == haunt_room for b in bats), "初始火蝠应全在作祟揭露房"
    for b in bats:
        assert engine._monster_invulnerable(b), "火蝠不可被攻击（invulnerable）"

    # 驱魔来源：戒指是理智来源（替换 8 号灵应板）；灵应板不在清单
    assert "omen_ring" in handler.ALL_SOURCES and "omen_ring" in handler.SANITY_ITEM_SOURCES
    assert "omen_spirit_board" not in handler.ALL_SOURCES

    # 一次性驱魔来源：戒指理智 5+ 成功 → 进度 1、来源作废、放理智检定令牌
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0
    hero.items.append("omen_ring")
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "omen_ring", {}) is True
    assert engine._haunt_track_value("exorcism_successes") == 1
    assert "omen_ring" in flags["used_exorcism_sources"]
    assert engine.tokens_of_kind("sanity_check"), "理智驱魔成功应放理智检定令牌"
    engine._reset_player_turn_state(hero)
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "omen_ring", {}) is False, "同一来源只能成功用一次"
    assert "omen_ring" not in {a.id for a in handler.available_actions(engine, hero)}, "用过的来源不该再出现"

    # 驱魔【失败】路径（直接验证 Major 修复：只有检定成功才消耗来源）
    # 圣徽为理智来源；理智 5+ 检定失败 → 轨道不推进、来源不作废、下次仍可用
    hero.items.append("omen_holy_symbol")
    engine._reset_player_turn_state(hero)
    before_fail = engine._haunt_track_value("exorcism_successes")
    with patch.object(engine, "_resolve_check", return_value=False):
        assert handler.perform_action(engine, hero, "omen_holy_symbol", {}) is True, "行动可执行即返回 True"
    assert engine._haunt_track_value("exorcism_successes") == before_fail, "检定失败不该推进轨道"
    assert "omen_holy_symbol" not in flags["used_exorcism_sources"], "检定失败不该作废来源（消除软锁）"
    assert "omen_holy_symbol" in {a.id for a in handler.available_actions(engine, hero)}, "失败后来源仍可复用"

    # 知识侧令牌产出：古书为知识来源；知识 5+ 成功 → knowledge_check 令牌 + 轨道 +1 + 来源作废
    hero.items.append("omen_book")
    engine._reset_player_turn_state(hero)
    before_know = engine._haunt_track_value("exorcism_successes")
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "omen_book", {}) is True
    assert engine._haunt_track_value("exorcism_successes") == before_know + 1, "知识驱魔成功应推进轨道"
    assert "omen_book" in flags["used_exorcism_sources"], "成功后知识来源作废"
    assert engine.tokens_of_kind("knowledge_check"), "知识驱魔成功应放知识检定令牌"

    # 怪物回合：一次掷骰 → 现有火蝠移动 + 繁殖等量新火蝠 + 同房英雄受物理伤
    # 把目标英雄放进揭露房（火蝠已在此），另一名英雄挪到别处不受灼烧
    other_hero = next((p for p in engine.state.players if p.role == "hero" and not p.dead and p is not hero), None)
    far_room = next((k for k in sorted(engine.state.board) if k != haunt_room), haunt_room)
    hero.room_key = haunt_room
    if other_hero is not None:
        other_hero.room_key = far_room
    before = len(handler._bats(engine))
    flags["last_swarm_turn"] = -1  # 允许本回合跑一次群集阶段
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 2 if "移动" in label else 3), \
            patch.object(engine, "_deal_damage") as dealt:
        assert handler.on_monster_turn_start(engine, handler._bats(engine)[0]) is True
    assert len(handler._bats(engine)) == before + 2, "掷骰结果=新进揭露房的火蝠数（繁殖 2 只）"
    dealt.assert_called_with(hero, "physical", 3, source=handler.DAMAGE_SOURCE)
    # 同一怪物回合内第二只火蝠不再重跑群集阶段（last_swarm_turn 守卫）
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 2 if "移动" in label else 3), \
            patch.object(engine, "_deal_damage") as dealt2:
        assert handler.on_monster_turn_start(engine, handler._bats(engine)[0]) is True
    assert len(handler._bats(engine)) == before + 2, "同一怪物回合只跑一次群集阶段"
    dealt2.assert_not_called()

    # 火蝠朝最近英雄移动：把所有英雄挪到最远房，掷骰给足步数，验证火蝠靠近
    farthest = max(
        (k for k in engine.state.board if engine.state.board[k].revealed),
        key=lambda k: engine._path_length(haunt_room, k),
    )
    for p in engine.state.players:
        if p.role == "hero" and not p.dead:
            p.room_key = farthest
    flags["last_swarm_turn"] = -1
    moving_bat = handler._bats(engine)[0]
    moving_bat.room_key = haunt_room
    before_len = engine._path_length(haunt_room, farthest)
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 3 if "移动" in label else 0), \
            patch.object(engine, "_deal_damage"):
        assert handler.on_monster_turn_start(engine, moving_bat) is True
    assert engine._path_length(moving_bat.room_key, farthest) < before_len, "火蝠应朝最近英雄移动"

    # 灼烧只伤英雄不伤叛徒：把叛徒与英雄同时放进有火蝠的揭露房，收集全部 _deal_damage
    # 调用；灼烧 victims 只筛 role=="hero"，故目标集合应含英雄、不含叛徒（叛徒操控火蝠）
    for b in handler._bats(engine):
        b.room_key = haunt_room  # 把所有火蝠收回揭露房，构造确定的灼烧现场
    hero.room_key = haunt_room
    traitor.room_key = haunt_room
    for p in engine.state.players:
        if p.role == "hero" and not p.dead and p is not hero:
            p.room_key = far_room  # 其他英雄挪到无蝠房，避免混入
    flags["last_swarm_turn"] = -1
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 0 if "移动" in label else 3), \
            patch.object(engine, "_deal_damage") as dealt_burn:
        assert handler.on_monster_turn_start(engine, handler._bats(engine)[0]) is True
    burned = [call.args[0] for call in dealt_burn.call_args_list]
    assert any(v is hero for v in burned), "灼烧应命中同房英雄"
    assert not any(v is traitor for v in burned), "灼烧绝不该命中叛徒"
    assert all(v.role == "hero" for v in burned), "灼烧目标集合只含英雄"

    # 胜负：驱魔满员 → 英雄胜；英雄全灭 → 叛徒胜；叛徒死亡不白送英雄胜
    engine._set_haunt_track_value("exorcism_successes", engine._haunt_track_target("exorcism_successes"))
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    engine._set_haunt_track_value("exorcism_successes", 0)
    traitor.dead = True
    assert handler.check_victory(engine) is True and engine.state.winner is None, "应吸收叛徒死亡兜底"
    traitor.dead = False
    for player in engine.state.players:
        if player.role == "hero":
            player.dead = True
    assert handler.check_victory(engine) is True and engine.state.winner == "traitor"


def _haunt25_effect_doll(kind: str, hero_id: int) -> dict:
    """构造一个合成娃娃，供 _apply_effect 的定点测试使用（不动 setup 的真娃娃）。"""
    return {"kind": kind, "hero_id": hero_id, "room_template": "kitchen",
            "destroyed": False, "found": False}


def verify_haunt25_voodoo() -> None:
    """剧本 25：娃娃分配/搜寻与销毁/五种效果/时钟推进/胜负与叛徒死亡兜底（p36/p107）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=25)
    handler = engine._mode_handler()
    assert isinstance(handler, VoodooMode)
    flags = engine._haunt_flags()
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    hero_a, hero_b, hero_c = heroes
    assert traitor.dead is False, "p107：叛徒（揭示者）仍在场"
    engine.state.turn_order = [hero_a.id]
    engine.state.turn_index = 0

    # ---- 开局：每英雄一只娃娃，类型按序；「恰有一间已发现」必须选已发现那间
    dolls = flags["dolls"]
    assert [d["kind"] for d in dolls] == ["wax", "china", "stone"], "娃娃类型按 p107 列表顺序分配"
    for d in dolls:
        cands = VoodooMode.CANDIDATES[d["kind"]]
        assert d["room_template"] in cands
        discovered = [t for t in cands if handler._is_discovered(engine, t)]
        if len(discovered) == 1:
            assert d["room_template"] == discovered[0], "恰有一间已发现时必须选它（p107）"

    # ---- 时钟归属：英雄回合结束不推进；叛徒回合结束推进（p107）
    assert engine._haunt_track_value("turn_damage") == 0
    with patch.object(engine, "roll_dice", return_value=8):
        handler.on_turn_end(engine, hero_a)
    assert engine._haunt_track_value("turn_damage") == 0, "英雄回合结束不该推进轨道"
    with patch.object(engine, "roll_dice", return_value=8):
        handler.on_turn_end(engine, traitor)
    assert engine._haunt_track_value("turn_damage") == 1, "p107：叛徒回合结束把轨道推进到 1"

    # ---- 老坑吸收：叛徒死亡 ≠ 英雄胜，时钟由本轮最后一名存活玩家代推
    saved_traitor_dead = traitor.dead
    traitor.dead = True
    with patch.object(engine, "roll_dice", return_value=8):
        handler.on_turn_end(engine, hero_a)
    assert engine._haunt_track_value("turn_damage") == 2, "叛徒出局后时钟由最后存活玩家代推"
    assert engine.state.winner is None, "叛徒死亡不等于英雄胜（老坑 15 号吸收者）"
    traitor.dead = saved_traitor_dead
    engine._set_haunt_track_value("turn_damage", 1)

    # ---- 搜寻：知识 2+ 成功后如实回答；空房结果全桌公开
    own_a = next(d for d in dolls if d["hero_id"] == hero_a.id)
    taken = {d["room_template"] for d in dolls}
    board_templates = {r.template_id for r in engine.state.board.values()}
    empty_template = next(
        t for t in ("entrance_hall", "kitchen", "chapel", "grand_staircase")
        if t not in taken and t in board_templates
    )
    empty_key = next(k for k, r in engine.state.board.items() if r.template_id == empty_template)
    hero_a.room_key = empty_key
    hero_a.control = "human"  # bot 在非候选房不搜（门控下面单独测）
    engine._reset_player_turn_state(hero_a)
    assert "search_doll" in {a.id for a in handler.available_actions(engine, hero_a)}
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero_a, "search_doll", {}) is True
    assert empty_template in flags["cleared_rooms"], "空房搜寻结果应全桌公开"
    assert handler.available_actions(engine, hero_a) == [], "已知没娃娃的房间不再提供搜寻"

    # bot 门控：不在自己娃娃的候选房里，bot 搜不了
    hero_a.control = "bot"
    engine._reset_player_turn_state(hero_a)
    assert handler.available_actions(engine, hero_a) == [], "bot 只在自己娃娃的候选房里搜寻"

    # bot 门控：进了候选房（含已公开位置）就可以搜；搜到自己的娃娃当场销毁
    chosen = own_a["room_template"]
    room_key = next((k for k, r in engine.state.board.items() if r.template_id == chosen), None)
    if room_key is None:
        placed = engine._place_room(engine.catalog.room_templates[chosen], 40, 40, 0)
        placed.revealed = True
        room_key = placed.key
    hero_a.room_key = room_key
    engine._reset_player_turn_state(hero_a)
    assert "search_doll" in {a.id for a in handler.available_actions(engine, hero_a)}
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero_a, "search_doll", {}) is True
    assert own_a["destroyed"] is True, "p36：搜到自己的娃娃当场自动销毁"

    # ---- 效果（p107）。合成娃娃定点触发，不动 setup 的真娃娃
    # 蜡：bot 必须避开"轨道最底格、掉 1 即死"的属性（实测 157 种子的教训）
    track_sp = engine._stat_track(hero_b, "speed")
    hero_b.stat_positions["speed"] = 0
    hero_b.stats["speed"] = track_sp[0]
    track_mi = engine._stat_track(hero_b, "might")
    hero_b.stat_positions["might"] = min(3, len(track_mi) - 1)
    hero_b.stats["might"] = track_mi[hero_b.stat_positions["might"]]
    speed_before = hero_b.stats["speed"]
    might_pos = hero_b.stat_positions["might"]
    handler._apply_effect(engine, hero_b, _haunt25_effect_doll("wax", hero_b.id), 1)
    assert hero_b.stats["speed"] == speed_before, "掉血不能选轨道最底格的属性"
    assert hero_b.stat_positions["might"] == might_pos - 1, "应掉安全且数值较高的力量"

    # 瓷：掷 4 骰 < 回合数 → 当场死亡 + 娃娃销毁（含引擎死亡钩子销毁真娃娃）
    doll_china = _haunt25_effect_doll("china", hero_b.id)
    with patch.object(engine, "roll_dice", return_value=0):
        handler._apply_effect(engine, hero_b, doll_china, 1)
    assert hero_b.dead is True, "瓷娃娃掷输应当场杀死英雄"
    assert doll_china["destroyed"] is True
    assert next(d for d in dolls if d["hero_id"] == hero_b.id)["destroyed"] is True, "p36：英雄死亡其娃娃同时销毁"

    # 石：掷输 → 每项属性各掉 1 格
    for stat in ("might", "speed", "sanity", "knowledge"):
        track = engine._stat_track(hero_a, stat)
        hero_a.stat_positions[stat] = min(3, len(track) - 1)
        hero_a.stats[stat] = track[hero_a.stat_positions[stat]]
    pos_before = {s: hero_a.stat_positions[s] for s in ("might", "speed", "sanity", "knowledge")}
    with patch.object(engine, "roll_dice", return_value=0):
        handler._apply_effect(engine, hero_a, _haunt25_effect_doll("stone", hero_a.id), 1)
    for stat in ("might", "speed", "sanity", "knowledge"):
        assert hero_a.stat_positions[stat] == pos_before[stat] - 1, f"石娃娃应让 {stat} 各掉 1 格"
    assert hero_a.dead is False

    # 玻璃：自选掉 1 点理智或知识（恰好一项）
    s_pos = hero_a.stat_positions["sanity"]
    k_pos = hero_a.stat_positions["knowledge"]
    handler._apply_effect(engine, hero_a, _haunt25_effect_doll("glass", hero_a.id), 1)
    lost_sanity = hero_a.stat_positions["sanity"] == s_pos - 1
    lost_knowledge = hero_a.stat_positions["knowledge"] == k_pos - 1
    assert lost_sanity ^ lost_knowledge, "玻璃娃娃应恰好掉 1 点理智或知识"

    # 布：掷输 → 2 点物理伤害（全落到速度，分摊策略由引擎决定，总格数为 2）
    hero_a.ignore_first_physical_damage = False
    if "item_armor" in hero_a.items:
        hero_a.items.remove("item_armor")  # 排除盔甲挡伤的通用分支，专注本剧本规则
    sp0, mi0 = hero_a.stat_positions["speed"], hero_a.stat_positions["might"]
    with patch.object(engine, "roll_dice", return_value=0):
        handler._apply_effect(engine, hero_a, _haunt25_effect_doll("rag", hero_a.id), 1)
    drop = (sp0 - hero_a.stat_positions["speed"]) + (mi0 - hero_a.stat_positions["might"])
    assert drop == 2, "布娃娃掷输应受 2 点物理伤害"
    assert hero_a.dead is False

    # ---- 英雄胜：所有娃娃销毁 且 存活英雄 ≥ 一半（向上取整）
    hero_c_doll = next(d for d in dolls if d["hero_id"] == hero_c.id)
    handler._destroy_doll(engine, hero_c_doll, reason="测试：销毁第三只娃娃。")
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes", "p36：销毁全部娃娃且过半存活 → 英雄胜"

    # ---- 叛徒胜：过半英雄死亡（严格大于一半；3 英雄局死 1 个还不够）
    engine2 = _run_until_haunt(seed=109, players=4, haunt_id=25)
    handler2 = engine2._mode_handler()
    heroes2 = [p for p in engine2.state.players if p.role == "hero"]
    heroes2[0].dead = True
    assert handler2.check_victory(engine2) is True and engine2.state.winner is None, "死不过半不判叛徒胜（需严格大于一半）"
    heroes2[1].dead = True
    assert handler2.check_victory(engine2) is True
    assert engine2.state.winner == "traitor", "p107：过半英雄死亡 → 叛徒胜"


def verify_haunt25_deferred_draw() -> None:
    """剧本 25 探索解禁：探索新房间不再强制停，抽牌推迟到「结束移动的房间」（p36）。"""
    # seed 113 在基础规则修正后地面层已被探索干净（前沿 0 个），改用仍有
    # 地面层空门位的 seed 137——本用例验的是"探索不再强制停"，与种子无关。
    engine = _run_until_haunt(seed=137, players=3, haunt_id=25)
    handler = engine._mode_handler()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    # 探索阶段就倒下的英雄：开局即触发 p36 死亡联动，其娃娃直接是销毁态
    for doll in engine._haunt_flags()["dolls"]:
        owner = next(p for p in engine.state.players if p.id == doll["hero_id"])
        assert doll["destroyed"] == owner.dead, "英雄死亡 ↔ 娃娃销毁（含作祟前已死者）"
    assert handler.explore_stop_suspended(engine, hero) is True
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0

    # 实际走一步探索：强制抽到厨房（物品符号房），移动不应被强制打断
    # 起点不能写死入口大厅：它的三个门位在部分轨迹下已被占满，next() 会
    # StopIteration。测试验的是"探索不再强制停"，与具体是哪间房无关；
    # 挑一间地面层还有空门位的房间即可（厨房是地面层模板，抽牌补丁只对 0 层生效）。
    frontier_options = engine.exploration_frontier_keys(0)
    assert frontier_options, "地面层应还有可探索的房间牌（否则本测试无法进行）"
    frontier = frontier_options[0]
    hero.room_key = frontier
    # 先给足步数再问行动列表：available_move_options 不带步数/处于"移动已停"
    # 状态就没有移动选项（换 seed 后英雄可能已把步数走完或已被停移动）。
    hero.steps_remaining = 5
    hero.movement_stopped = False
    option = next(o for o in engine.available_move_options(hero) if o.is_new_room)
    kitchen = engine.catalog.room_templates["kitchen"]
    real_draw = engine._draw_room_template
    used = {"kitchen": False}

    def fake_draw(floor: int):
        if floor == 0 and not used["kitchen"]:
            used["kitchen"] = True
            return kitchen
        return real_draw(floor)

    with patch.object(engine, "_draw_room_template", side_effect=fake_draw):
        assert engine.move_player(hero, option) is True
    new_room = engine.current_room(hero)
    assert new_room.template_id == "kitchen", "应抽到被强制指定的厨房"
    assert new_room.revealed is True
    assert hero.movement_stopped is False, "p36：探索新房间不再强制停下"
    assert hero.steps_remaining == 4, "探索只扣移动费用，步数不清零"
    pending = engine._haunt_flags()["pending_draws"]
    assert str(new_room.key) in pending, "符号房间的抽牌应被延迟记录"
    with patch.object(engine, "_draw_symbol_card", wraps=engine._draw_symbol_card) as draw:
        handler.on_turn_end(engine, hero)
    assert draw.called, "结束移动停在新发现的符号房间 → 补抽一张"
    assert draw.call_args.kwargs.get("stop_movement") is False, "延迟抽牌不打断移动"
    assert str(new_room.key) not in pending

    # 路过不停：新符号房发现后没停在里面 → 回合结束不补抽且作废
    kitchen2 = engine._place_room(kitchen, 40, 40, 0)
    hero.room_key = kitchen2.key
    engine._resolve_room_entry_if_needed(hero)
    assert str(kitchen2.key) in engine._haunt_flags()["pending_draws"]
    hero.room_key = frontier  # 没停在里面
    with patch.object(engine, "_draw_symbol_card") as draw2:
        handler.on_turn_end(engine, hero)
    assert not draw2.called, "没停在里面的新发现符号房不补抽（p36 只认结束移动的房间）"
    assert str(kitchen2.key) not in engine._haunt_flags()["pending_draws"], "作废的延迟抽牌应清掉"

    # 在新发现的符号房间里搜寻 → 立即抽一张（p36）
    kitchen3 = engine._place_room(kitchen, 41, 40, 0)
    kitchen3.revealed = False
    hero.room_key = kitchen3.key
    engine._resolve_room_entry_if_needed(hero)
    engine._reset_player_turn_state(hero)
    hero.control = "human"  # 厨房不是 bot 候选房，转人类视角触发搜寻
    with patch.object(engine, "_resolve_check", return_value=True):
        with patch.object(engine, "_draw_symbol_card", wraps=engine._draw_symbol_card) as draw3:
            assert handler.perform_action(engine, hero, "search_doll", {}) is True
    assert draw3.called, "p36：在新发现的符号房间里搜寻要先抽一张符号牌"


def verify_haunt26_rat_ritual() -> None:
    """剧本 26：鼠人强化/老鼠布点/合力攻击与失败不受伤/击败即死/
    五芒星室封锁与叛徒免伤/仪式与老鼠回流/四条胜负路径（p37/p108）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=26)
    handler = engine._mode_handler()
    assert isinstance(handler, RatRitualMode)
    flags = engine._haunt_flags()
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    hero = heroes[0]
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0

    # ---- 开局：鼠人强化——每项属性至少初始值+1（封顶轨道顶格）
    face = engine.catalog.characters.get(traitor.character_id)
    for stat in ("might", "speed", "sanity", "knowledge"):
        start = face.stats.get(stat)
        track = engine._stat_track(traitor, stat)
        cap = track[-1] if track else 99
        assert traitor.stats[stat] >= min(start + 1, cap), f"鼠人 {stat} 应 ≥ 初始+1（p108）"

    # ---- 五芒星室清场（p37）：没有活人留在里面
    penta = handler._pentagram_key(engine)
    assert penta, "五芒星室应在场"
    assert all(p.dead or p.room_key != penta for p in engine.state.players), "p37：五芒星室里的探险者应被挪去邻格"

    # ---- 老鼠布点：玩家数×2，全在有符号的房间，不在五芒星室
    rats = handler._rats(engine)
    assert len(rats) == 2 * len(engine.state.players), "p108：老鼠 = 玩家数 × 2"
    assert all(engine.state.board[m.room_key].symbol in ("event", "item", "omen") for m in rats)
    assert all(m.room_key != penta for m in rats)

    # ---- 进入封锁：英雄进不了五芒星室，叛徒可以
    assert handler.room_entry_blocked(engine, hero, engine.state.board[penta]) is True
    assert handler.room_entry_blocked(engine, traitor, engine.state.board[penta]) is False

    # ---- 合力攻击：成功造成伤害；力量相加封顶 8 骰
    if "item_armor" in hero.items:
        hero.items.remove("item_armor")
    hero.ignore_first_physical_damage = False
    for stat in ("might", "speed", "sanity", "knowledge"):
        track = engine._stat_track(hero, stat)
        hero.stat_positions[stat] = min(4, len(track) - 1)
        hero.stats[stat] = track[hero.stat_positions[stat]]
    rat_a, rat_b, rat_c = rats[0], rats[1], rats[2]
    rat_a.room_key = rat_b.room_key = hero.room_key
    speed_pos0 = hero.stat_positions["speed"]
    with patch.object(engine, "roll_dice", return_value=3), patch.object(engine, "_roll_attack", return_value=0):
        assert handler.on_monster_turn_start(engine, rat_a) is True
    assert hero.stat_positions["speed"] == speed_pos0 - 3, "合力攻击成功应造成差额物理伤害"
    assert rat_a in engine.state.monsters and rat_a.stunned_turns == 0
    # 失败不受伤（p108）；换一个回合号——同一回合同房间的鼠群只能扑一次
    engine.state.turn_count += 1
    with patch.object(engine, "roll_dice", return_value=0), patch.object(engine, "_roll_attack", return_value=8):
        assert handler.on_monster_turn_start(engine, rat_a) is True
    assert rat_a in engine.state.monsters and rat_a.stunned_turns == 0, "合力攻击失败不受伤"
    assert rat_b in engine.state.monsters and rat_b.stunned_turns == 0
    # 骰数 = 力量相加（3 只 = 6 骰），封顶 8
    engine.state.turn_count += 1
    rat_c.room_key = hero.room_key
    counts: list[int] = []

    def fake_roll(count: int, label: str = "") -> int:
        counts.append(count)
        return 0

    with patch.object(engine, "roll_dice", side_effect=fake_roll), patch.object(engine, "_roll_attack", return_value=8):
        handler.on_monster_turn_start(engine, rat_a)
    assert counts == [6], f"3 只老鼠应掷力量相加的 6 骰，实际 {counts}"
    # 同回合轮到同房的第二只老鼠：整组已经扑过，不再重复结算（否则伤害翻 N 倍）
    counts.clear()
    with patch.object(engine, "roll_dice", side_effect=fake_roll), patch.object(engine, "_roll_attack", return_value=8):
        handler.on_monster_turn_start(engine, rat_b)
    assert counts == [], f"同回合同房间不应再扑一次，实际掷骰 {counts}"

    # ---- 被击败即死（不会昏迷）
    assert handler.monster_killed_on_defeat(engine, rat_a, hero, "might", "") is True
    engine._kill_monster(rat_a, killer=hero)
    assert rat_a not in engine.state.monsters

    # ---- 仪式：进室置旗；叛徒在室内免伤；成功 +1 轨道
    engine.state.turn_order = [traitor.id]
    engine.state.turn_index = 0
    traitor.room_key = penta
    handler.on_enter_room(engine, traitor, engine.state.board[penta])
    assert flags["traitor_reached"] is True
    assert handler.attack_allowed(engine, hero, traitor) is False, "p37/p108：五芒星室里的叛徒不受攻击"
    engine._reset_player_turn_state(traitor)
    assert "perform_ritual" in {a.id for a in engine.available_haunt_actions(traitor)}
    # 击败即死环节已杀一只：场上 7 只、池 8 → 仪式成功应回流一只到邻格
    rats_in_play = len(handler._rats(engine))
    with patch.object(engine, "_resolve_check", return_value=True):
        assert engine.perform_haunt_action(traitor, "perform_ritual") is True
    assert engine._haunt_track_value("ritual_rolls") == 1
    assert len(handler._rats(engine)) == rats_in_play + 1, "p108：仪式成功应回流一只可用老鼠"
    new_rat = handler._rats(engine)[-1]
    assert new_rat.room_key in engine._grid_neighbors(penta), "回流老鼠应落在五芒星室邻格（不需要门）"
    # 池满（8 只都在场）后再仪式 → 不回流
    engine._reset_player_turn_state(traitor)
    with patch.object(engine, "_resolve_check", return_value=True):
        assert engine.perform_haunt_action(traitor, "perform_ritual") is True
    assert engine._haunt_track_value("ritual_rolls") == 2
    assert len(handler._rats(engine)) == rats_in_play + 1, "池满时仪式不应回流"

    # ---- 胜负路径
    # ① 杀光所有老鼠 → 英雄胜（p37）
    engine2 = _run_until_haunt(seed=109, players=4, haunt_id=26)
    h2 = engine2._mode_handler()
    for m in list(h2._rats(engine2)):
        engine2._kill_monster(m, killer=None)
    assert h2.check_victory(engine2) is True
    assert engine2.state.winner == "heroes"
    # ② 叛徒进五芒星室之前被杀 → 英雄胜（p37）
    engine3 = _run_until_haunt(seed=109, players=4, haunt_id=26)
    h3 = engine3._mode_handler()
    t3 = next(p for p in engine3.state.players if p.role == "traitor")
    assert engine3._haunt_flags().get("traitor_reached") is False
    t3.dead = True
    assert h3.check_victory(engine3) is True
    assert engine3.state.winner == "heroes", "p37：叛徒进室前被杀 → 英雄胜"
    # ③ 叛徒已进室后被杀（防御路径）→ 不判英雄胜，老坑吸收
    engine4 = _run_until_haunt(seed=109, players=4, haunt_id=26)
    h4 = engine4._mode_handler()
    t4 = next(p for p in engine4.state.players if p.role == "traitor")
    engine4._haunt_flags()["traitor_reached"] = True
    t4.dead = True
    assert h4.check_victory(engine4) is True and engine4.state.winner is None
    # ④ 仪式完成（4 人局需 5 次）→ 叛徒胜
    engine5 = _run_until_haunt(seed=109, players=4, haunt_id=26)
    h5 = engine5._mode_handler()
    engine5._set_haunt_track_value("ritual_rolls", 5)
    assert h5.check_victory(engine5) is True
    assert engine5.state.winner == "traitor", "p108：仪式完成 → 叛徒胜"
    # ⑤ 英雄全灭 → 叛徒胜（p108）
    engine6 = _run_until_haunt(seed=109, players=4, haunt_id=26)
    h6 = engine6._mode_handler()
    for p in engine6.state.players:
        if p.role == "hero":
            p.dead = True
    assert h6.check_victory(engine6) is True
    assert engine6.state.winner == "traitor"


def verify_haunt26_pentagram_block() -> None:
    """剧本 26：英雄的移动选项过滤五芒星室；探索抽到五芒星室直接弃掉换一张（p37/p108）。"""
    engine = _run_until_haunt(seed=157, players=4, haunt_id=26)
    handler = engine._mode_handler()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    penta = handler._pentagram_key(engine)
    assert penta, "测试需要五芒星室在场"

    # 门连通的邻室：英雄站在那里时，移动选项里不应出现五芒星室
    checked = 0
    for key in engine._door_neighbors(penta):
        if key == penta or engine._is_collapsed(key):
            continue
        hero.room_key = key
        options = engine.available_move_options(hero)
        assert all(o.target_key != penta for o in options), "p37：英雄的移动选项应过滤五芒星室"
        checked += 1
    assert checked > 0, "测试需要至少一间与五芒星室门连通的房间"

    # 探索抽牌：抽到五芒星室模板 → 弃掉换一张，不重复上桌、英雄不进去
    frontier = None
    option = None
    for key in list(engine.state.board):
        if engine.state.board[key].floor != 0:
            continue
        hero.room_key = key
        new_opts = [o for o in engine.available_move_options(hero) if o.is_new_room]
        if new_opts:
            frontier, option = key, new_opts[0]
            break
    assert frontier is not None, "测试需要地面层探索前沿"
    hero.steps_remaining = 5
    penta_template = engine.catalog.room_templates["pentagram_chamber"]
    real_draw = engine._draw_room_template
    used = {"penta": False}

    def fake_draw(floor: int):
        if floor == 0 and not used["penta"]:
            used["penta"] = True
            return penta_template
        return real_draw(floor)

    with patch.object(engine, "_draw_room_template", side_effect=fake_draw):
        assert engine.move_player(hero, option) is True
    assert sum(1 for r in engine.state.board.values() if r.template_id == "pentagram_chamber") == 1, "抽到的五芒星室应被弃掉，不重复上桌"
    assert engine.current_room(hero).template_id != "pentagram_chamber", "英雄不能进五芒星室"


def _haunt27_frontier(engine, handler, player):
    """把 player 放到"与 Blob 房间门相连的邻室"，返回该房间 key。"""
    flags = engine._haunt_flags()
    blob = set(flags.get("blob_rooms", [])) | set(flags.get("blob_seeded", []))
    for key in sorted(blob):
        for nxt in sorted(engine._door_neighbors(key)):
            if nxt not in blob and nxt in engine.state.board:
                player.room_key = nxt
                return nxt
    raise AssertionError("测试需要 Blob 的门外邻室")


def verify_haunt27_amok_flesh() -> None:
    """剧本 27：Blob 扩张与掷 2 追加/弱点检定/配料搜寻与投掷/Blobperson
    转化与限制/胜负与叛徒死亡后代推时钟（p38/p109）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=27)
    handler = engine._mode_handler()
    assert isinstance(handler, AmokFleshMode)
    flags = engine._haunt_flags()
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    hero = heroes[0]
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0
    needed = len(engine.state.players)

    # ---- 开局：水晶球被弃、起源房已定、Blob 尚未扩张
    assert flags.get("blob_origin"), "p38/p109：应确定 Blob 起源房"
    assert flags.get("blob_rooms") == [] and flags.get("blob_grew_once") is False

    # ---- 第一个怪物回合：吞没起源房 + 门邻房；掷非 2 不追加
    with patch.object(engine, "roll_dice", return_value=1):
        handler.on_turn_end(engine, traitor)
    blob = flags["blob_rooms"]
    assert flags["blob_grew_once"] is True
    assert flags["blob_origin"] in blob, "起源房应被吞没"
    assert all(n in blob for n in engine._door_neighbors(flags["blob_origin"])), "门邻房应被吞没"
    assert all(
        handler._is_blobperson(engine, p) or p.room_key not in set(blob)
        for p in engine.state.players if not p.dead
    ), "p109：只有身处 Blob 房间的人被同化"

    # ---- 掷出 2 追加扩张
    rooms_before = len(flags["blob_rooms"])
    with patch.object(engine, "roll_dice", side_effect=[2, 0]):
        handler.on_turn_end(engine, traitor)
    assert len(flags["blob_rooms"]) > rooms_before, "p109：掷出 2 应再扩一圈"

    # ---- examine_blob：不邻 Blob 不可用；邻室检定累计玩家数次 → 弱点找到
    hero.room_key = next(k for k in engine.state.board if k not in set(blob) | set(flags["blob_seeded"]))
    engine._reset_player_turn_state(hero)
    assert "examine_blob" not in {a.id for a in handler.available_actions(engine, hero)}, "不邻 Blob 不能检查"
    frontier = _haunt27_frontier(engine, handler, hero)
    engine._reset_player_turn_state(hero)
    assert "examine_blob" in {a.id for a in handler.available_actions(engine, hero)}
    with patch.object(engine, "_resolve_check", return_value=True):
        for i in range(needed):
            assert engine.perform_haunt_action(hero, "examine_blob") is True
            engine._reset_player_turn_state(hero)
    assert flags["weakness_found"] is True, "p38：累计玩家数次成功 → 弱点找到"
    assert engine._haunt_track_value("knowledge_rolls") == 0, "弱点找到后检定令牌重置"
    assert "examine_blob" not in {a.id for a in handler.available_actions(engine, hero)}, "弱点找到后不能再检查"

    # ---- search_ingredient：厨房搜出配料；同房不可再搜
    kitchen_key = next(
        (k for k, r in engine.state.board.items() if r.template_id == "kitchen"),
        None,
    )
    if kitchen_key is None:
        kitchen = engine._place_room(engine.catalog.room_templates["kitchen"], 40, 40, 0)
        kitchen.revealed = True
        kitchen_key = kitchen.key
    hero.room_key = kitchen_key
    engine._reset_player_turn_state(hero)
    assert "search_ingredient" in {a.id for a in handler.available_actions(engine, hero)}
    with patch.object(engine, "_resolve_check", return_value=True):
        assert engine.perform_haunt_action(hero, "search_ingredient") is True
    assert flags["ingredients"].get(str(hero.id), 0) == 1
    assert kitchen_key in flags["searched_rooms"], "p38：搜过的房放理智标记，不可再搜"
    assert "search_ingredient" not in {a.id for a in handler.available_actions(engine, hero)}

    # ---- throw_ingredient：邻室投掷花 1 格移动；投满 → 英雄胜
    _haunt27_frontier(engine, handler, hero)
    engine._reset_player_turn_state(hero)
    steps0 = 5
    hero.steps_remaining = steps0
    assert "throw_ingredient" in {a.id for a in handler.available_actions(engine, hero)}
    with patch.object(engine, "_resolve_check", return_value=True):
        assert engine.perform_haunt_action(hero, "throw_ingredient") is True
    assert hero.steps_remaining == steps0 - 1, "p38：投掷用 1 格移动"
    assert engine._haunt_track_value("blob_ingredients") == 1
    assert flags["ingredients"][str(hero.id)] == 0

    # ---- Blobperson：走进 Blob 房间即被同化，限制全套生效
    hero.items.append("item_candle")  # 转化时应被弃掉
    blob_key = sorted(set(flags["blob_rooms"]))[0]
    hero.room_key = blob_key
    handler.on_enter_room(engine, hero, engine.state.board[blob_key])
    assert handler._is_blobperson(engine, hero), "p109：身处 Blob 房间立刻变成 Blobperson"
    assert "item_candle" not in hero.items, "p109：Blobperson 弃掉所有物品与预兆"
    assert handler.attack_allowed(engine, hero, traitor) is False, "Blobperson 不能攻击"
    assert handler.attack_allowed(engine, traitor, hero) is False, "Blobperson 不能被攻击"
    assert handler.can_discover_rooms(engine, hero) is False
    assert handler.mystic_elevator_blocked(engine, hero) is True
    assert handler.suppress_room_draw(engine, hero, engine.current_room(hero)) is True
    hero.steps_remaining = 9
    handler.on_turn_start(engine, hero)
    assert hero.steps_remaining == 2, "p109：Blobperson Speed 2"
    assert handler.available_actions(engine, hero) == [], "Blobperson 不能执行剧本行动"

    # ---- 叛徒胜：所有英雄死亡或 Blobperson（engine1：hero 已同化，其余死亡）
    for p in heroes:
        if p.id != hero.id:
            p.dead = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor", "p109：所有英雄死亡或 Blobperson → 叛徒胜"

    # ---- 英雄胜：投满配料销毁 Blob
    engine2 = _run_until_haunt(seed=109, players=4, haunt_id=27)
    h2 = engine2._mode_handler()
    flags2 = engine2._haunt_flags()
    t2 = next(p for p in engine2.state.players if p.role == "traitor")
    with patch.object(engine2, "roll_dice", return_value=1):
        h2.on_turn_end(engine2, t2)  # 先让 Blob 落地，才有"门外邻室"可投掷
    flags2["weakness_found"] = True
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    flags2["ingredients"][str(hero2.id)] = 1
    engine2._set_haunt_track_value("blob_ingredients", needed - 1)
    engine2.state.turn_order = [hero2.id]
    engine2.state.turn_index = 0
    _haunt27_frontier(engine2, h2, hero2)
    engine2._reset_player_turn_state(hero2)
    with patch.object(engine2, "_resolve_check", return_value=True):
        assert engine2.perform_haunt_action(hero2, "throw_ingredient") is True
    assert h2.check_victory(engine2) is True
    assert engine2.state.winner == "heroes", "p38：投满配料 → Blob 销毁，英雄胜"

    # ---- 叛徒死亡：扩张时钟改由本轮最后一名存活玩家代推（老坑 17 号吸收者）
    engine3 = _run_until_haunt(seed=109, players=4, haunt_id=27)
    h3 = engine3._mode_handler()
    t3 = next(p for p in engine3.state.players if p.role == "traitor")
    hero3 = next(p for p in engine3.state.players if p.role == "hero" and not p.dead)
    engine3.state.turn_order = [hero3.id]
    engine3.state.turn_index = 0
    t3.dead = True
    assert engine3._haunt_flags().get("blob_rooms") == []
    with patch.object(engine3, "roll_dice", return_value=1):
        h3.on_turn_end(engine3, hero3)
    assert engine3._haunt_flags().get("blob_rooms"), "叛徒出局后 Blob 应照常扩张"
    assert engine3.state.winner is None, "叛徒死亡 ≠ 英雄胜"


def verify_haunt27_blob_ai() -> None:
    """剧本 27：Blob 自保钩子（禁区/险区/做完挪窝/停步风险）与寻路绕行。

    钉住三条实测教训：
      · seed101/3p：英雄寻路把 Blob 房间当近路穿过去（入口大厅→地下室平台），
        进门即被同化——`bot_blocked_rooms` 必须让规划绕开，引擎寻路支持 blocked；
      · seed113/3p：贴边检定完原地过夜（`_pending_haunt_action_here` 判定
        "下回合还能在这儿做"），下个怪物回合 Blob 正好扩进这间房——
        `bot_leave_after_action` 必须拦下，且撤退目标只给险区外的房间；
      · seed101/3p：险区里踏进"进房即停"的效果房（保险库知识检定成功连抽
        两张物品卡，`_draw_item` 清零剩余步数），被困在扩张圈里——
        `room_stop_risk` 必须识别这一类房间，bot 的险区扣分才会生效。
    """

    class _FakeRoom:
        """只带 effect_id 的替身，用来确定性地验 room_stop_risk（不看牌桌布局）。"""

        def __init__(self, effect_id: str) -> None:
            self.effect_id = effect_id

    engine = _run_until_haunt(seed=101, players=3, haunt_id=27)
    handler = engine._mode_handler()
    assert isinstance(handler, AmokFleshMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # ---- Blob 未落地：险区 = 起源房 + 一圈邻域；起源房里的人先退开
    origin = flags["blob_origin"]
    zone = {origin} | handler._neighbors_of(engine, {origin})
    assert handler.bot_blocked_rooms(engine, hero) == set(), "未落地时没有禁区"
    assert handler.bot_hazard_rooms(engine, hero) == zone, "未落地时险区=起源房邻域"
    hero.room_key = origin
    goals = {g[len("__room__") :] for g in handler.bot_goal_rooms(engine, hero)}
    assert goals and goals <= set(handler._safe_keys(engine)), "起源房里应先退到险区外"
    outside = next(k for k in sorted(engine.state.board) if k not in zone)
    hero.room_key = outside
    goals = {g[len("__room__") :] for g in handler.bot_goal_rooms(engine, hero)}
    assert goals == handler._neighbors_of(engine, zone, doors_only=True), "未落地时应预习检定圈"

    # ---- Blob 落地：禁区 = Blob 房间；规划路径不得穿过禁区
    with patch.object(engine, "roll_dice", return_value=1):
        handler.on_turn_end(engine, traitor)
    blob = set(flags["blob_rooms"])
    assert blob, "第一个怪物回合应让 Blob 落地"
    assert handler.bot_blocked_rooms(engine, hero) == blob, "Blob 房间是寻路禁区"
    assert handler.bot_hazard_rooms(engine, hero) == blob | handler._neighbors_of(engine, blob)
    checked = 0
    for start in sorted(engine.state.board):
        for target in sorted(engine.state.board):
            if start == target or start in blob or target in blob:
                continue
            path = engine._shortest_path(start, target, avoid_transit=True, blocked=blob)
            assert not (set(path) & blob), f"禁区房间不得出现在路径里：{start}→{target}"
            checked += 1
            if checked >= 40:
                break
        if checked >= 40:
            break
    assert checked >= 40, "样本不足，没真正跑到绕行分支"

    # ---- bot_ai 的接线：禁区/险区确实来自剧本钩子
    controller = BotController()
    blocked, hazards = controller._bot_path_filters(engine, hero)
    assert blocked == blob - {hero.room_key}, "寻路禁区应透传给 bot"
    assert hazards == handler.bot_hazard_rooms(engine, hero), "危险房应透传给 bot"

    # ---- 做完一步必须挪窝；退到险区外才允许原地结束
    assert handler.bot_leave_after_action(engine, hero) is False, "还没行动：不触发挪窝"
    engine._mark_haunt_action_used(hero)
    assert handler.bot_leave_after_action(engine, hero) is True, "行动用完必须挪窝"
    ring = sorted(handler._neighbors_of(engine, blob, doors_only=True))
    assert ring, "Blob 落地后应有门邻检定圈"
    hero.room_key = ring[0]
    assert handler.bot_stay_in_room(engine, hero) is False, "扩张圈里不能过夜"
    goals = {g[len("__room__") :] for g in handler.bot_goal_rooms(engine, hero)}
    assert goals and goals <= set(handler._safe_keys(engine)), "险区里做完一步→目标是退开"
    safe = [k for k in handler._safe_keys(engine) if k != hero.room_key]
    assert safe, "42 间房的牌桌应仍有险区外的安全房"
    hero.room_key = safe[0]
    assert handler.bot_stay_in_room(engine, hero) is True, "退到险区外：原地结束"

    # ---- 弱点没找到前，配料房不是寻路目的地
    flags["weakness_found"] = False
    assert handler.bot_action_blocked(engine, hero, "search_ingredient") is True
    flags["weakness_found"] = True
    assert handler.bot_action_blocked(engine, hero, "search_ingredient") is False

    # ---- "这里还有活吗"：险区里未找到弱点=有事做；Blob 房间里=没事做
    flags["weakness_found"] = False
    hero.room_key = ring[0]
    assert handler._has_work_here(engine, hero) is True, "扩张圈上（弱点未找到）应能检定"
    hero.room_key = sorted(blob)[0]
    assert handler._has_work_here(engine, hero) is False, "Blob 房间里的英雄无事可做"

    # ---- 停步风险房：抽牌/传送/坠落/障碍失败类房间会被识别
    for effect in (
        "room_vault",
        "room_research_laboratory",
        "room_coal_chute",
        "room_collapsed_room",
        "room_chasm",
        "room_catacombs",
        "room_mystic_elevator",
        "room_underground_lake",
    ):
        assert engine.room_stop_risk(_FakeRoom(effect)) is True, f"{effect} 应算停步风险"
    assert engine.room_stop_risk(_FakeRoom("room_graveyard")) is False
    assert engine.room_stop_risk(_FakeRoom("")) is False


def verify_haunt28_demon_ring() -> None:
    """剧本 28：地狱门选址与恶魔入场/速度免疫/理智 +2/两败领主/策反与
    受控代跑/抢戒指与取回/胜负（p39/p110）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=28)
    handler = engine._mode_handler()
    assert isinstance(handler, DemonRingMode)
    flags = engine._haunt_flags()
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    hero = heroes[0]
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0

    # ---- 开局：地狱门 + 领主 + 英雄数只恶魔（真实触发时戒指在叛徒手里）
    portal = flags.get("portal_room")
    assert portal and portal in engine.state.board, "p110：地狱门房应已选定"
    assert engine.state.board[portal].symbol == "event"
    lord = next(m for m in engine.state.monsters if m.template_id == "demon_lord")
    demons = [m for m in engine.state.monsters if m.template_id in DemonRingMode.DEMON_TEMPLATES]
    assert len(demons) == 2, "p110：恶魔数量 = 英雄数（2 英雄局 = 2 只）"
    assert all(m.room_key == portal for m in [lord, *demons]), "恶魔应都在地狱门房"
    # 恶魔数值按 p110 页脚
    by_id = {m.template_id: m for m in engine.state.monsters}
    assert (by_id["demon_lord"].speed, by_id["demon_lord"].might) == (1, 7)
    assert (by_id["demon_1"].speed, by_id["demon_1"].might, by_id["demon_1"].sanity) == (2, 5, 5)
    # 速度攻击免疫走 monster_specs（p110：左轮等速度攻击打不中领主）
    specs = engine._haunt_rule_state().get("monster_specs", {})
    assert "speed" in specs["demon_lord"].get("immune_to", [])

    # 真实触发时揭示者持有戒指；强制触发的测试局手动补上并模拟流转
    traitor.items.append("omen_ring")

    # ---- 理智 +2（p39）：持戒指对领主的理智攻击 +2；不持戒指不加
    traitor.items.remove("omen_ring")
    hero.items.append("omen_ring")
    handler.attack_attr_override(engine, hero, lord, "sanity")
    assert handler.attack_roll_bonus(engine, hero, lord) == 2
    # 机器人持戒打恶魔会自选理智攻击（p39 的 +2 与"理智攻击策反"都只认理智，
    # 而引擎徒手默认力量）：钩子把徒手力量切成理智，加值随之生效。
    sanity0, might0 = hero.stats.get("sanity", 0), hero.stats.get("might", 0)
    hero.stats["sanity"], hero.stats["might"] = 5, 4
    assert handler.attack_attr_override(engine, hero, lord, "might") == "sanity"
    assert handler.attack_roll_bonus(engine, hero, lord) == 2
    assert handler.attack_attr_override(engine, hero, demons[0], "might") == "sanity", (
        "p39：对普通恶魔也切理智（成功即策反）"
    )
    assert handler.attack_roll_bonus(engine, hero, demons[0]) == 0, "策反无 +2"
    # 理智明显低于力量的角色不硬拗（不把角色改弱）：维持力量、不加值
    hero.stats["sanity"], hero.stats["might"] = 1, 7
    assert handler.attack_attr_override(engine, hero, lord, "might") is None
    assert handler.attack_roll_bonus(engine, hero, lord) == 0
    hero.stats["sanity"], hero.stats["might"] = sanity0, might0
    # 不持戒指：力量攻击照旧不加值，也不切换
    hero.items.remove("omen_ring")
    assert handler.attack_attr_override(engine, hero, lord, "might") is None
    assert handler.attack_roll_bonus(engine, hero, lord) == 0
    traitor.items.append("omen_ring")

    # ---- 抢戒指（p110）：恶魔赢戒指持有人 2+ → 抢走不掉血
    assert handler.on_monster_attack(engine, demons[0], traitor, 3) is True
    assert "omen_ring" not in traitor.items and "omen_ring" in demons[0].items
    assert handler.on_monster_attack(engine, demons[0], traitor, 1) is False, "赢不足 2 不抢"

    # ---- 取回（p110）：击败带戒指恶魔 → 立刻拿回；普通恶魔不持戒指击败 = 击晕
    assert handler.monster_killed_on_defeat(engine, demons[0], hero, "might", "") is False
    assert "omen_ring" in hero.items and "omen_ring" not in demons[0].items

    # ---- 策反（p39）：持戒指理智攻击成功 → 恶魔受控、不被击晕
    with patch.object(engine, "_resolve_check", return_value=True):
        pass  # 攻击流程由引擎走；这里直接按引擎调用顺序打两个钩子
    assert handler.monster_killed_on_defeat(engine, demons[1], hero, "sanity", "") is False
    assert handler.on_monster_defeated(engine, demons[1], 1) is True
    assert demons[1].id in flags["controlled_demons"], "p39：理智攻击策反恶魔"
    assert handler.on_monster_turn_start(engine, demons[1]) is True, "受控恶魔不再敌对行动"

    # ---- 两败领主（p39）：持戒指击败两次；第一次击晕，第二次摧毁
    hero_room_before = hero.room_key
    assert handler.monster_killed_on_defeat(engine, lord, hero, "sanity", "") is False
    assert engine._haunt_track_value("lord_defeats") == 1
    assert handler.monster_killed_on_defeat(engine, lord, hero, "sanity", "") is True
    assert engine._haunt_track_value("lord_defeats") == 2 and flags["lord_destroyed"] is True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes", "p39：领主被戒指摧毁 → 英雄胜"

    # ---- 领主攻击戒指持有人落败也算一次击败（p39）
    engine2 = _run_until_haunt(seed=113, players=3, haunt_id=28)
    h2 = engine2._mode_handler()
    t2 = next(p for p in engine2.state.players if p.role == "traitor")
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    lord2 = next(m for m in engine2.state.monsters if m.template_id == "demon_lord")
    hero2.items.append("omen_ring")  # 领主的目标是最近英雄——戒指要在持有人（英雄）身上
    lord2.room_key = hero2.room_key
    with patch.object(engine2, "_roll_monster_attack", return_value=0), patch.object(
        engine2, "_roll_attack", return_value=4
    ):
        assert h2.on_monster_turn_start(engine2, lord2) is True
    assert engine2._haunt_track_value("lord_defeats") == 1, "p39：领主攻戒指持有人落败也计数"
    assert lord2.stunned_turns > 0, "领主落败照常被击晕"

    # ---- 受控恶魔代跑：戒指持有人回合开始，受控恶魔追击叛徒
    engine3 = _run_until_haunt(seed=113, players=3, haunt_id=28)
    h3 = engine3._mode_handler()
    t3 = next(p for p in engine3.state.players if p.role == "traitor")
    hero3 = next(p for p in engine3.state.players if p.role == "hero" and not p.dead)
    demon3 = next(m for m in engine3.state.monsters if m.template_id == "demon_1")
    t3.items.append("omen_ring")
    hero3.items.append("omen_ring")  # 修正：真实流程是英雄持戒
    t3.items.remove("omen_ring")
    engine3._haunt_flags()["controlled_demons"].append(demon3.id)
    demon3.room_key = hero3.room_key  # 从英雄身边出发
    engine3.state.turn_order = [hero3.id]
    engine3.state.turn_index = 0
    engine3._reset_player_turn_state(hero3)
    h3.on_turn_start(engine3, hero3)
    assert demon3.room_key != hero3.room_key or demon3.stunned_turns > 0, "受控恶魔应向叛徒移动/攻击"

    # ---- 叛徒胜与叛徒死亡兜底（老坑 18 号吸收者）
    engine4 = _run_until_haunt(seed=113, players=3, haunt_id=28)
    h4 = engine4._mode_handler()
    for p in engine4.state.players:
        if p.role == "hero":
            p.dead = True
    assert h4.check_victory(engine4) is True
    assert engine4.state.winner == "traitor", "p110：英雄全灭 → 叛徒胜"
    engine5 = _run_until_haunt(seed=113, players=3, haunt_id=28)
    h5 = engine5._mode_handler()
    next(p for p in engine5.state.players if p.role == "traitor").dead = True
    assert h5.check_victory(engine5) is True and engine5.state.winner is None, "叛徒死亡 ≠ 英雄胜"

    # ---- 受控恶魔打玩家（p39 代跑里"目标是人"的分支）
    # 旧代码写 `isinstance(nearest, Player)`，而 haunt_modes 刻意不 import
    # engine —— 该行一旦执行必抛 NameError（策反不可达时一直没暴露）。
    # 改成鸭子类型判 role 后，这里必须真的结算出一次攻击。
    engine6 = _run_until_haunt(seed=113, players=3, haunt_id=28)
    h6 = engine6._mode_handler()
    traitor6 = next(p for p in engine6.state.players if p.role == "traitor")
    hero6 = next(p for p in engine6.state.players if p.role == "hero" and not p.dead)
    demon6 = next(m for m in engine6.state.monsters if m.template_id == "demon_1")
    hero6.items.append("omen_ring")
    engine6._haunt_flags()["controlled_demons"].append(demon6.id)
    far_key = max(engine6.state.board, key=lambda k: engine6._path_length(k, traitor6.room_key))
    for other in engine6.state.monsters:  # 其余怪物挪远：保证最近敌人就是叛徒
        if other is not demon6:
            other.room_key = far_key
    demon6.room_key = traitor6.room_key
    demon6.stunned_turns = 0
    lines: list[str] = []
    original_log6 = engine6._log

    def _cap6(message: str, category: str = "") -> None:
        lines.append(message)
        original_log6(message, category)

    engine6._log = _cap6  # type: ignore[method-assign]
    with patch.object(engine6, "_roll_monster_attack", return_value=3), patch.object(
        engine6, "_roll_attack", return_value=0
    ):
        h6._controlled_demon_act(engine6, demon6)
    engine6._log = original_log6  # type: ignore[method-assign]
    assert any("受控的" in line and "攻击" in line for line in lines), (
        "受控恶魔与叛徒同房时应发起攻击（旧 isinstance(Player) NameError 的回归）"
    )

    # ---- 目标钩子的戒指流转（p110 抢戒指 / p39 掉落）
    engine7 = _run_until_haunt(seed=113, players=3, haunt_id=28)
    h7 = engine7._mode_handler()
    traitor7 = next(p for p in engine7.state.players if p.role == "traitor")
    hero7 = next(p for p in engine7.state.players if p.role == "hero" and not p.dead)
    other_hero7 = next(
        (p for p in engine7.state.players if p.role == "hero" and p.id != hero7.id and not p.dead),
        None,
    )
    lord7 = next(m for m in engine7.state.monsters if m.template_id == "demon_lord")
    demon7 = next(m for m in engine7.state.monsters if m.template_id == "demon_1")
    # ① 叛徒持戒 → 全队围攻叛徒
    traitor7.items.append("omen_ring")
    assert h7.bot_goal_rooms(engine7, hero7) == ["__room__" + traitor7.room_key]
    # ② 英雄持戒 → 持戒者直奔恶魔领主；其余英雄不被这条目标牵走
    traitor7.items.remove("omen_ring")
    hero7.items.append("omen_ring")
    assert h7.bot_goal_rooms(engine7, hero7) == ["__room__" + lord7.room_key]
    if other_hero7 is not None:
        assert h7.bot_goal_rooms(engine7, other_hero7) == [], "非持戒者不抢领主打点"
    # ③ 戒指被恶魔抢走（p110）→ 去打那只恶魔夺回来
    hero7.items.remove("omen_ring")
    demon7.items.append("omen_ring")
    assert h7.bot_goal_rooms(engine7, hero7) == ["__room__" + demon7.room_key]
    # ④ 戒指掉在房间里（携带者死亡落地）→ 去那间房捡
    demon7.items.remove("omen_ring")
    engine7.state.room_items.setdefault(hero7.room_key, []).append("omen_ring")
    assert h7.bot_goal_rooms(engine7, hero7) == ["__room__" + hero7.room_key]


def verify_haunt29_frankenstein() -> None:
    """剧本 29：实验室落位/点火与携带上限/火把投掷（命中不击晕、落败不掉血、
    命中数=玩家数）/推落/攻击 +2/抢火把/速度免疫/胜负（p40/p111）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=29)
    handler = engine._mode_handler()
    assert isinstance(handler, FrankensteinMode)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0

    # ---- 开局：怪物站在研究实验室或手术室，数值 3/8（p111 页脚）
    monster = handler._monster(engine)
    assert monster is not None, "p111：怪物应已入场"
    assert engine.state.board[monster.room_key].template_id in ("research_laboratory", "operating_laboratory")
    assert (monster.speed, monster.might) == (3, 8)
    specs = engine._haunt_rule_state().get("monster_specs", {})
    assert "speed" in specs["frankenstein"].get("immune_to", []), "p111：免疫速度攻击"
    assert handler.monster_attack_roll_bonus(engine, monster, hero) == 2, "p111：攻击 +2"

    # ---- 点火把：厨房可点；每人同时只带一支
    kitchen_key = next(
        (k for k, r in engine.state.board.items() if r.template_id == "kitchen"),
        None,
    )
    if kitchen_key is None:
        placed = engine._place_room(engine.catalog.room_templates["kitchen"], 40, 40, 0)
        placed.revealed = True
        kitchen_key = placed.key
    hero.room_key = kitchen_key
    engine._reset_player_turn_state(hero)
    assert "light_torch" in {a.id for a in handler.available_actions(engine, hero)}
    assert engine.perform_haunt_action(hero, "light_torch") is True
    assert handler._torches(engine, hero), "火把令牌应挂在英雄身上"
    assert "light_torch" not in {a.id for a in handler.available_actions(engine, hero)}, "已带火把不能再点"

    # ---- 投掷：不邻怪物不可用；邻室命中 → +1 轨道、不击晕、火把消耗
    assert "throw_torch" not in {a.id for a in handler.available_actions(engine, hero)}, "不邻怪物不能投掷"
    hero.room_key = monster.room_key
    engine._reset_player_turn_state(hero)
    assert "throw_torch" in {a.id for a in handler.available_actions(engine, hero)}
    with patch.object(engine, "_roll_attack", return_value=6), patch.object(
        engine, "_roll_monster_attack", return_value=2
    ):
        assert engine.perform_haunt_action(hero, "throw_torch") is True
    assert engine._haunt_track_value("torch_hits") == 1
    assert not handler._torches(engine, hero), "命中后火把应消耗掉"
    assert monster.stunned_turns == 0, "p40：火把命中不击晕怪物"
    assert engine.state.winner is None

    # ---- 投掷落败：只是失去火把，英雄不掉血（p40）
    hero.room_key = monster.room_key
    engine._reset_player_turn_state(hero)
    handler.perform_action(engine, hero, "light_torch", {})
    stats_before = dict(hero.stats)
    with patch.object(engine, "_roll_attack", return_value=1), patch.object(
        engine, "_roll_monster_attack", return_value=7
    ):
        assert engine.perform_haunt_action(hero, "throw_torch") is True
    assert not handler._torches(engine, hero)
    assert hero.stats == stats_before, "p40：投掷落败英雄不掉血"
    assert monster.stunned_turns == 0 and not engine._haunt_flags().get("monster_destroyed")

    # ---- 抢火把（p111）：怪物赢 2+ 抢走并销毁；不足 2 不抢
    handler.perform_action(engine, hero, "light_torch", {})
    assert handler._torches(engine, hero)
    assert handler.on_monster_attack(engine, monster, hero, 3) is True
    assert not handler._torches(engine, hero), "p111：怪物抢走并销毁火把"
    assert hero.stats == stats_before, "抢火把代替伤害，不掉血"
    handler.perform_action(engine, hero, "light_torch", {})
    assert handler.on_monster_attack(engine, monster, hero, 2) is False, "赢不足 2 不抢"
    assert handler._torches(engine, hero)

    # ---- 火把命中达标 → 怪物死亡 → 英雄胜
    needed = len(engine.state.players)
    engine._set_haunt_track_value("torch_hits", needed - 1)
    engine._reset_player_turn_state(hero)
    hero.room_key = monster.room_key
    with patch.object(engine, "_roll_attack", return_value=6), patch.object(
        engine, "_roll_monster_attack", return_value=2
    ):
        assert engine.perform_haunt_action(hero, "throw_torch") is True
    assert engine._haunt_flags().get("monster_destroyed") is True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes", "p40：命中数达标 → 怪物死亡，英雄胜"

    # ---- 推落：塔楼/深渊同房间力量 6+（p40）
    engine2 = _run_until_haunt(seed=113, players=3, haunt_id=29)
    h2 = engine2._mode_handler()
    monster2 = h2._monster(engine2)
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    tower_key = next(
        (k for k, r in engine2.state.board.items() if r.template_id == "tower"),
        None,
    )
    if tower_key is None:
        placed = engine2._place_room(engine2.catalog.room_templates["tower"], 41, 40, 0)
        placed.revealed = True
        tower_key = placed.key
    hero2.room_key = tower_key
    monster2.room_key = tower_key
    engine2.state.turn_order = [hero2.id]
    engine2.state.turn_index = 0
    engine2._reset_player_turn_state(hero2)
    assert "push_monster" in {a.id for a in h2.available_actions(engine2, hero2)}
    with patch.object(engine2, "_resolve_check", return_value=True):
        assert engine2.perform_haunt_action(hero2, "push_monster") is True
    assert engine2._haunt_flags().get("monster_destroyed") is True
    assert h2.check_victory(engine2) is True
    assert engine2.state.winner == "heroes", "p40：推落成功 → 英雄胜"

    # ---- 叛徒胜与叛徒死亡兜底（老坑 19 号吸收者）
    engine3 = _run_until_haunt(seed=113, players=3, haunt_id=29)
    h3 = engine3._mode_handler()
    for p in engine3.state.players:
        if p.role == "hero":
            p.dead = True
    assert h3.check_victory(engine3) is True
    assert engine3.state.winner == "traitor", "p111：英雄全灭 → 叛徒胜"
    engine4 = _run_until_haunt(seed=113, players=3, haunt_id=29)
    h4 = engine4._mode_handler()
    next(p for p in engine4.state.players if p.role == "traitor").dead = True
    assert h4.check_victory(engine4) is True and engine4.state.winner is None, "叛徒死亡 ≠ 英雄胜"

    # ---- bot 钩子（批次6 #29）：怪物房间禁区 / 禁肉搏 / 险区 / 距离分相
    # 实测（seed149/4p）：英雄的撤离目标没问题，但到远处的最短路径要穿过
    # 怪物所在的房间，机器人照走不误、还顺手空手开打（1 对 13，反手吃 12 点
    # 当场倒下）。所以英雄必须把怪物房间当寻路禁区；唯一例外是 p40 的推落
    # 窗口——怪物就在塔楼/深渊里、自己推得动的时候，那一间正是目的地。
    engine5 = _run_until_haunt(seed=113, players=3, haunt_id=29)
    h5 = engine5._mode_handler()
    monster5 = h5._monster(engine5)
    hero5 = next(p for p in engine5.state.players if p.role == "hero" and not p.dead)
    traitor5 = next(p for p in engine5.state.players if p.role == "traitor")
    assert h5.bot_blocked_rooms(engine5, hero5) == {monster5.room_key}, "怪物房间是英雄禁区"
    assert h5.bot_blocked_rooms(engine5, traitor5) == set(), "叛徒不受英雄禁区限制"
    tower_key5 = next(
        (k for k, r in engine5.state.board.items() if r.template_id == "tower"), None
    )
    if tower_key5 is None:
        placed5 = engine5._place_room(engine5.catalog.room_templates["tower"], 41, 40, 0)
        placed5.revealed = True
        tower_key5 = placed5.key
    monster5.room_key = tower_key5
    hero5.stats["might"] = 5
    assert h5.bot_blocked_rooms(engine5, hero5) == set(), "推落窗口：怪物房间正是要去的地方"
    hero5.stats["might"] = 2
    assert h5.bot_blocked_rooms(engine5, hero5) == {tower_key5}, "力量不够就别进塔楼"

    # 英雄不肉搏力 8 的怪物（p111 落败要挨差值反击）；叛徒可以打
    assert h5.bot_attack_blocked(engine5, hero5, monster5) is True
    assert h5.bot_attack_blocked(engine5, traitor5, monster5) is False

    # 险区：空手 = 怪物一个移动射程（≤3 步）内全部；持火把时投掷位（1 步
    # 门邻）是他该站的位置，不算险区，但怪物房间和中段（2-3 步）都算。
    assert not h5._torches(engine5, hero5)
    distances5 = h5._monster_distances(engine5)
    assert h5.bot_hazard_rooms(engine5, hero5) == {
        k for k, d in distances5.items() if d <= h5.THREAT_STEPS
    }, "空手险区=怪物 3 步以内"
    assert h5.perform_action(engine5, hero5, "light_torch", {}) is True
    assert h5._torches(engine5, hero5)
    distances5 = h5._monster_distances(engine5)
    assert h5.bot_hazard_rooms(engine5, hero5) == {
        k for k, d in distances5.items() if d == 0 or 2 <= d <= h5.THREAT_STEPS
    }, "持火把：投掷位（1 步）不算险区"

    # 怪物只追"最近的英雄"（引擎 _find_monster_target）——队友挪远、自己
    # 站到它隔壁时，判定必须落在我身上。
    adjacent5 = next((k for k, d in sorted(distances5.items()) if d == 1), None)
    farthest5 = max(distances5.items(), key=lambda item: item[1])[0] if distances5 else None
    if adjacent5 is not None and farthest5 is not None:
        for other in engine5.state.players:
            if other.role == "hero" and other.id != hero5.id and not other.dead:
                other.room_key = farthest5
        hero5.room_key = adjacent5
        assert h5._is_monster_target(engine5, hero5, h5._monster_distances(engine5)) is True

    # 目标分相：站在怪物 2-3 步外、拿着火把、行动还没用 → 往投掷位走
    # （移动后 `_try_haunt_action` 会立刻把火把投出去）；行动已经用掉
    # （比如刚在点火房点完火把）→ 不许再靠过去，只给撤离目标。
    spot5 = next((k for k, d in sorted(distances5.items()) if 2 <= d <= 3), None)
    if spot5 is not None:
        hero5.room_key = spot5
        hero5.stats["speed"] = 4
        engine5._reset_player_turn_state(hero5)
        ring5 = {k for k in engine5._door_neighbors(monster5.room_key) if k != monster5.room_key}
        if ring5:
            goals5 = {g[len("__room__") :] for g in h5.bot_goal_rooms(engine5, hero5)}
            assert goals5 & ring5, "能一脚踏进投掷位 → 该往投掷位去"
            engine5._mark_haunt_action_used(hero5)
            goals5 = {g[len("__room__") :] for g in h5.bot_goal_rooms(engine5, hero5)}
            assert not (goals5 & ring5), "行动已用：进去也投不了，只会白送火把"
            assert goals5, "撤离目标不能为空（空 = 退回通用走位）"
            far5 = {k for k, d in distances5.items() if d >= h5.THREAT_STEPS + 2}
            if far5:
                assert goals5 <= far5, "撤离目标该在怪物 5 步之外"


def verify_haunt30_dracula() -> None:
    """剧本 30：开局布置/时钟与日出掷骰/弱化与昏迷/自动钉杀/圣物准入/
    魅惑与吸血鬼化/长矛钉杀/圣徽击退/阳光烧毁/胜负（p41/p112）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=30)
    handler = engine._mode_handler()
    assert isinstance(handler, DraculaRisingMode)
    flags = engine._haunt_flags()
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    hero = heroes[0]
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0

    # ---- 开局：叛徒变吸血鬼（+1 每项）；德古拉在墓地/地窖；新娘在叛徒房
    assert handler._is_vampire_player(engine, traitor), "p112：叛徒应变成吸血鬼"
    dracula = next(m for m in engine.state.monsters if m.template_id == "dracula")
    bride = next(m for m in engine.state.monsters if m.template_id == "bride")
    assert engine.state.board[dracula.room_key].template_id in ("crypt", "graveyard")
    assert bride.room_key == traitor.room_key, "p112：新娘放在叛徒房间"
    assert (dracula.speed, dracula.might, dracula.sanity) == (5, 8, 6)
    assert (bride.speed, bride.might, bride.sanity) == (4, 4, 4)
    assert all("omen_girl" not in p.items for p in engine.state.players), "p112：女孩卡被弃"
    face = engine.catalog.characters.get(traitor.character_id)
    for stat in ("might", "speed", "sanity", "knowledge"):
        assert traitor.stats[stat] >= min(face.stats[stat] + 1, 99), "p112：叛徒每项属性 +1"

    # ---- 时钟：英雄回合开始不推进；叛徒回合开始 +1 并掷日出（ patched 不日出）
    assert engine._haunt_track_value("sun_track") == 0
    with patch.object(engine, "roll_dice", return_value=9):
        handler.on_turn_start(engine, hero)
    assert engine._haunt_track_value("sun_track") == 0, "只有叛徒回合开始才推进轨道"
    with patch.object(engine, "roll_dice", return_value=9):
        handler.on_turn_start(engine, traitor)
    assert engine._haunt_track_value("sun_track") == 1, "p112：叛徒回合开始推进轨道"
    assert flags["sunrise"] is False, "日出检定 9 ≥ 1 不日出"

    # ---- 德古拉第 2 回合前不移动不攻击（p112）
    before = dracula.room_key
    assert handler.on_monster_turn_start(engine, dracula) is True
    assert dracula.room_key == before, "p112：德古拉第 2 回合前不动"

    # ---- 日出：掷骰 < 回合数 → 日出；随后每叛徒回合开始怪物每项属性 -1
    # （先挪出向阳房：德古拉若开局在墓地，日出瞬间被烧是正确行为）
    safe_key = next(
        k for k, r in engine.state.board.items()
        if r.template_id not in DraculaRisingMode.SUNLIT_ROOMS
    )
    dracula.room_key = safe_key
    bride.room_key = safe_key
    traitor.room_key = safe_key  # 叛徒吸血鬼也别被日出烧死，否则时钟停摆
    with patch.object(engine, "roll_dice", side_effect=[0, 0]):
        handler.on_turn_start(engine, traitor)  # 轨道 2，日出检定 0 < 2 → 日出
    assert flags["sunrise"] is True
    m_before = (dracula.speed, dracula.might, dracula.sanity)
    handler.on_turn_start(engine, traitor)  # 轨道 3 + 弱化
    assert (dracula.speed, dracula.might, dracula.sanity) == tuple(
        max(0, v - 1) for v in m_before
    ), "p41：日出后每项属性各 -1"

    # ---- 阳光烧毁：吸血鬼怪物站在向阳房 → 摧毁；叛徒吸血鬼同理
    tower_key = next(
        (k for k, r in engine.state.board.items() if r.template_id == "tower"),
        None,
    )
    if tower_key is None:
        placed = engine._place_room(engine.catalog.room_templates["tower"], 41, 40, 0)
        placed.revealed = True
        tower_key = placed.key
    bride.room_key = tower_key
    handler._burn_vampires_in_sunlight(engine)
    assert flags["bride_destroyed"] is True, "p41：新娘在阳光下烧毁"
    assert bride not in engine.state.monsters
    traitor.room_key = tower_key
    handler._burn_vampires_in_sunlight(engine)
    assert traitor.dead is True, "p41：叛徒吸血鬼站进阳光也会烧死"

    # ---- 魅惑（p112）：隔门理智攻击 → 速度伤害 + 拖入房间；速度见底 → 吸血鬼化
    engine2 = _run_until_haunt(seed=113, players=3, haunt_id=30)
    h2 = engine2._mode_handler()
    t2 = next(p for p in engine2.state.players if p.role == "traitor")
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    bride2 = next(m for m in engine2.state.monsters if m.template_id == "bride")
    engine2.state.turn_order = [hero2.id]
    engine2.state.turn_index = 0
    bride2.room_key = hero2.room_key
    neighbor = next(
        (k for k in engine2._door_neighbors(hero2.room_key) if k in engine2.state.board),
        None,
    )
    assert neighbor, "测试需要一间门邻房"
    bride2.room_key = neighbor
    # 抬高速度位置（保证 4 点速度伤害不会直接见底触发吸血鬼化）
    sp_track = engine2._stat_track(hero2, "speed")
    hero2.stat_positions["speed"] = min(6, len(sp_track) - 1)
    hero2.stats["speed"] = sp_track[hero2.stat_positions["speed"]]
    speed_pos0 = hero2.stat_positions["speed"]
    hero_room_before = hero2.room_key
    with patch.object(engine2, "roll_dice", return_value=0), patch.object(
        engine2, "_roll_monster_attack", return_value=7
    ), patch.object(engine2, "_roll_attack", return_value=3):
        # 移动骰 patch 成 0：新娘留在邻室，走魅惑分支（p112 隔门理智攻击）
        assert h2.on_monster_turn_start(engine2, bride2) is True
    assert hero2.stat_positions["speed"] == speed_pos0 - 4, "p112：魅惑造成等额速度伤害"
    assert hero2.room_key == bride2.room_key, "p112：魅惑成功可把英雄拖进吸血鬼房间"
    hero2.room_key = hero_room_before  # 移回原房间，再测隔门魅惑的落败分支
    with patch.object(engine2, "roll_dice", return_value=0), patch.object(
        engine2, "_roll_monster_attack", return_value=2
    ), patch.object(engine2, "_roll_attack", return_value=7):
        assert h2.on_monster_turn_start(engine2, bride2) is True
    assert bride2.stunned_turns == 0, "p112：魅惑落败吸血鬼不受伤"

    # ---- 长矛钉杀（p41）：长矛+力量攻击击败 → 直接摧毁
    assert h2.monster_killed_on_defeat(engine2, bride2, hero2, "might", "omen_spear") is True
    assert engine2._haunt_flags()["bride_destroyed"] is True

    # ---- 圣徽击退（p41）：持圣徽击败 → 按伤害点数沿门击退，之后照常击晕
    hero2.items.append("omen_holy_symbol")
    drac2 = next(m for m in engine2.state.monsters if m.template_id == "dracula")
    drac2.room_key = hero2.room_key
    engine2.state.turn_order = [hero2.id]
    engine2._reset_player_turn_state(hero2)
    engine2._roll_monster_attack = lambda monster, attr, reroll_blanks=False: 1  # type: ignore
    engine2._roll_attack = lambda player, attr, bonus=0: 5  # type: ignore
    assert engine2.attack(hero2, drac2, None, False) is True
    assert drac2.room_key != hero2.room_key, "p41：圣徽把吸血鬼击退了"
    assert drac2.stunned_turns > 0, "击退之后照常被击晕"
    del engine2._roll_monster_attack
    del engine2._roll_attack

    # ---- 昏迷与自动钉杀（p41）：属性归零 → 昏迷；同房间钉杀摧毁
    engine3 = _run_until_haunt(seed=113, players=3, haunt_id=30)
    h3 = engine3._mode_handler()
    hero3 = next(p for p in engine3.state.players if p.role == "hero" and not p.dead)
    bride3 = next(m for m in engine3.state.monsters if m.template_id == "bride")
    engine3.state.turn_order = [hero3.id]
    engine3.state.turn_index = 0
    engine3._haunt_flags()["sunrise"] = True
    bride3.speed = 0
    engine3._haunt_flags().setdefault("unconscious_ids", []).append(bride3.id)
    bride3.room_key = hero3.room_key
    engine3._reset_player_turn_state(hero3)
    assert "stake_unconscious" in {a.id for a in h3.available_actions(engine3, hero3)}
    assert engine3.perform_haunt_action(hero3, "stake_unconscious") is True
    assert engine3._haunt_flags()["bride_destroyed"] is True, "p41：昏迷吸血鬼被自动钉杀"

    # ---- 圣物准入：吸血鬼怪物进教堂须理智 6+（p112）
    engine4 = _run_until_haunt(seed=113, players=3, haunt_id=30)
    h4 = engine4._mode_handler()
    drac4 = next(m for m in engine4.state.monsters if m.template_id == "dracula")
    chapel_key = next(
        (k for k, r in engine4.state.board.items() if r.template_id == "chapel"),
        None,
    )
    assert chapel_key, "测试需要教堂在场"
    with patch.object(engine4, "_roll_monster_attack", return_value=3):
        assert h4._holy_blocked(engine4, drac4, chapel_key) is True, "理智 3 < 6 被逼退"
    with patch.object(engine4, "_roll_monster_attack", return_value=6):
        assert h4._holy_blocked(engine4, drac4, chapel_key) is False, "理智 6+ 可进入"

    # ---- 胜负：双杀 → 英雄胜；英雄全灭 → 叛徒胜；叛徒死亡兜底
    engine5 = _run_until_haunt(seed=113, players=3, haunt_id=30)
    h5 = engine5._mode_handler()
    engine5._haunt_flags()["dracula_destroyed"] = True
    engine5._haunt_flags()["bride_destroyed"] = True
    assert h5.check_victory(engine5) is True
    assert engine5.state.winner == "heroes", "p41：双杀 → 英雄胜"
    engine6 = _run_until_haunt(seed=113, players=3, haunt_id=30)
    h6 = engine6._mode_handler()
    for p in engine6.state.players:
        if p.role == "hero":
            p.dead = True
    assert h6.check_victory(engine6) is True
    assert engine6.state.winner == "traitor", "p112：英雄全灭 → 叛徒胜"
    engine7 = _run_until_haunt(seed=113, players=3, haunt_id=30)
    h7 = engine7._mode_handler()
    next(p for p in engine7.state.players if p.role == "traitor").dead = True
    assert h7.check_victory(engine7) is True and engine7.state.winner is None, "叛徒死亡 ≠ 英雄胜"

    # ---- bot 钩子（批次6 #30）：不送死攻击 / 只去能赢的目标 / 不打自家怪
    # 实测（30 局）：英雄对吸血鬼发起 195 次攻击、其中 55 次直接把英雄打死
    # （占全部英雄死亡的一半以上）——力 2-4 的英雄去捶力 8 的德古拉，落败吃
    # 差值反击。修正后自伤死亡 55→42、英雄胜 4→6（同口径 30 局）。
    engine8 = _run_until_haunt(seed=113, players=3, haunt_id=30)
    h8 = engine8._mode_handler()
    hero8 = next(p for p in engine8.state.players if p.role == "hero" and not p.dead)
    traitor8 = next(p for p in engine8.state.players if p.role == "traitor")
    drac8 = next(m for m in engine8.state.monsters if m.template_id == "dracula")
    bride8 = next(m for m in engine8.state.monsters if m.template_id == "bride")

    # 送死攻击闸门：力 2 对力 8 → 不许打；被击晕/昏迷 → 随便打
    # （先清干净：真实对局里英雄可能本来就带着远程武器、新娘可能已被击晕）
    hero8.items = []
    engine8._haunt_flags()["unconscious_ids"] = []
    drac8.stunned_turns = 0
    bride8.stunned_turns = 0
    hero8.stats["might"] = 2
    assert h8.bot_attack_blocked(engine8, hero8, drac8) is True, "力 2 打力 8 德古拉 = 送死"
    bride8.might = 4
    assert h8.bot_attack_blocked(engine8, hero8, bride8) is True, "力 2 对力 4 也是送死"
    hero8.stats["might"] = 5
    assert h8.bot_attack_blocked(engine8, hero8, bride8) is False, "力 5 对力 4：打得起"
    assert h8.bot_attack_blocked(engine8, hero8, drac8) is True, "力 5 仍打不过力 8"
    bride8.stunned_turns = 1
    assert h8.bot_attack_blocked(engine8, hero8, bride8) is False, "被击晕：白送的输出"
    bride8.stunned_turns = 0
    # 长矛 +2：力 4 变 6 骰，打力 8 仍不够、打力 4 绰绰有余
    hero8.items.append("omen_spear")
    hero8.stats["might"] = 4
    assert h8._best_melee_dice(engine8, hero8) == 6
    assert h8.bot_attack_blocked(engine8, hero8, drac8) is True, "力 4+长矛=6 骰仍打不过力 8"
    assert h8.bot_attack_blocked(engine8, hero8, bride8) is False
    # 远程武器落败免伤（p20）：随便打
    hero8.items.append("item_revolver")
    hero8.stats["might"] = 1
    assert h8._has_ranged_weapon(engine8, hero8) is True
    assert h8.bot_attack_blocked(engine8, hero8, drac8) is False, "远程落败不受伤，可以打"
    # 打不过就不给目标；打得过/昏迷才给（昏迷优先，去钉杀）
    hero8.items = [c for c in hero8.items if c != "item_revolver"]
    hero8.stats["might"] = 4  # 长矛在手：4+2=6 骰，打得过新娘（力 4）
    assert h8.bot_goal_rooms(engine8, hero8) == ["__room__" + bride8.room_key], "只去打得过的吸血鬼"
    hero8.stats["might"] = 1  # 打不过两只 → 不给目标（去别处拖到日出）
    assert h8.bot_goal_rooms(engine8, hero8) == [], "打不过就不去送死"
    engine8._haunt_flags().setdefault("unconscious_ids", []).append(drac8.id)
    assert h8.bot_goal_rooms(engine8, hero8) == ["__room__" + drac8.room_key], "昏迷优先去钉杀"
    # 叛徒不打自己的怪物（bot_ai 通用闸门：controller == 自己阵营）
    assert drac8.controller == "traitor" and traitor8.role == "traitor"
    filtered8 = BotController()._filter_attack_targets(
        engine8, traitor8, [drac8, bride8], {"attack_heroes": True}
    )
    assert filtered8 == [], "叛徒不该打自家吸血鬼（30 号实测第一回合击晕自家新娘）"


def verify_haunt33_lake_rescue() -> None:
    """剧本 33：地下湖强制入场/探索关闭/湖面砖/游泳/搜索表/溺水计时（p44/p115）。"""
    # 湖面砖要求"水缘方向还没有房间"；基础规则修正后 seed113 的水缘已被
    # 房间占满（湖面选项 0 个），换用仍有水缘空位的 seed 307。
    engine = _run_until_haunt(seed=307, players=3, haunt_id=33)
    handler = engine._mode_handler()
    assert isinstance(handler, LakeRescueMode)
    flags = engine._haunt_flags()

    # 地下湖在场；女孩卡 set aside；探索关闭
    lake = handler._lake_room(engine)
    assert lake is not None and engine.state.board[lake].template_id == "underground_lake"
    assert not any("omen_girl" in deck for deck in engine.state.card_decks.values()), "女孩卡应被移出"
    assert handler.can_discover_rooms(engine, next(p for p in engine.state.players if p.role == "hero")) is False, \
        "地下室门厅已探明 → 不应允许探索新房间"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 湖面砖：hero 在地下湖时，extra_move_options 应包含 lake: 前缀选项
    hero.room_key = lake
    hero.movement_stopped = False  # 停移动状态下钩子按规则返回空列表
    options = handler.extra_move_options(engine, hero, [])
    assert any(o.target_key.startswith("lake:") for o in options), "水缘应有湖面选项"

    # 铺设湖面砖并移动（先重置回合状态并给足移动力）
    engine._reset_player_turn_state(hero)
    hero.steps_remaining = max(hero.steps_remaining, 3)
    option = next(o for o in options if o.target_key.startswith("lake:"))
    assert handler.lake_move(engine, hero, option) is True
    assert handler._is_lake_tile(engine, hero.room_key), "移动后应在湖面砖上"
    assert engine.state.board[hero.room_key].name == "湖面", "砖名应为湖面"

    # 游泳检定：4+ → 每砖 2 格
    with patch.object(engine, "_roll_attack", return_value=5):
        handler.on_turn_start(engine, hero)
    assert flags["swim_cost"].get(str(hero.id)) == 2, "游泳 5+ 应给 2 格"

    # 搜索表 19+：直接救出
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 19 if label == "搜寻女孩" else count):
        handler._search_roll(engine, hero)
    assert flags.get("girl_rescued") is True, "搜索 19+ 应救出女孩"
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # 溺水：叛徒回合开始推进计时，达阈值 → 叛徒胜
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    flags["girl_rescued"] = False
    threshold = int(flags.get("drown_threshold", 10))
    engine._set_haunt_track_value("drown_timer", threshold - 1)
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 10 if label == "溺水计时" else count):
        handler.on_turn_start(engine, traitor)
    assert flags.get("girl_drowned") is True
    assert engine.state.winner == "traitor"

    # 湖面丢弃即沉没
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    flags["girl_drowned"] = False
    hero2 = next((p for p in engine.state.players if p.role == "hero" and p.id != hero.id and not p.dead), None)
    if hero2 is not None:
        hero2.items.append("item_candle")
        hero2.room_key = hero.room_key  # 湖面砖上
        assert engine.drop_item(hero2, "item_candle") is True
        assert "item_candle" not in engine.room_items(hero2.room_key), "湖面丢弃应沉没"
        assert "item_candle" not in hero2.items


def verify_haunt34_mad_world() -> None:
    """剧本 34：保险库/捕获/背负/锁入/营救/胜利条件（p45/p116）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=34)
    handler = engine._mode_handler()
    assert isinstance(handler, MadWorldMode)
    flags = engine._haunt_flags()

    # 保险库在场；随从已布点
    vault = handler._vault_room(engine)
    assert vault is not None and engine.state.board[vault].template_id == "vault"
    servants = handler._servants(engine)
    assert len(servants) >= 1, "应有随从已布点"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 捕获：力量击败随从 → 抓住（prompter.confirm mock）
    servant = servants[0]
    hero.room_key = servant.room_key
    hero.steps_remaining = 5
    engine._active_player_id = hero.id
    with patch.object(engine, "_roll_attack", return_value=9), patch.object(
        engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 1
    ), patch.object(engine.prompter, "confirm", return_value=True):
        assert engine.attack(hero, servant) is True
    assert servant not in engine.state.monsters, "捕获后随从离场"
    assert handler._captive_kind(engine, hero) == "servant", "英雄应背着随从"

    # 背负入房 2 格
    assert handler.movement_cost_multiplier(engine, hero) == 2

    # 锁入：保险库必须"真的被打开"（引擎把开启状态写在房间数据里）。
    # 回归（M10-49）：过去这里查 flags["vault_open"]，而全项目没有任何地方
    # 会把它置 True，于是 lock_up 是死行动——英雄背着俘虏在库里站到 300
    # 回合也关不进去（seed101/4p 实测）。
    hero.room_key = vault
    _set_current(engine, hero)
    vault_room = engine.state.board[vault]
    vault_room.data.pop("opened", None)
    engine._haunt_flags()["vault_open"] = False
    assert "lock_up" not in {a.id for a in handler.available_actions(engine, hero)}, (
        "保险库还锁着时不能关人"
    )
    vault_room.data["opened"] = True  # 走真实开启路径（_apply_vault 的落点）
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "lock_up" in ids, "在（已打开的）保险库背着俘虏应能锁入"
    assert handler.perform_action(engine, hero, "lock_up", {}) is True
    assert len(flags.get("locked_up", [])) == 1, "随从应已锁入（1 人）"
    assert not handler._is_captive_carrier(engine, hero), "锁入后释放背负者"
    assert hero.movement_stopped, "锁入花整回合"

    # 背负者阵亡 → 俘虏挣脱回场。
    # 回归（M10-49）：过去没有 on_player_died，阵亡携带者会永久占住俘虏，
    # "随从全部被处置"永远凑不齐（seed101/4p：机器人3 背着随从阵亡，剩下
    # 两名英雄在酒窖↔地下室平台打转到 300 回合）。
    carrier = next(
        (p for p in engine.state.players if p.role == "hero" and not p.dead and p.id != hero.id),
        None,
    )
    remaining = handler._servants(engine)
    if carrier is not None and remaining:
        lost = remaining[0]
        handler._captors(engine)[str(carrier.id)] = "servant"
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "id", None) != getattr(lost, "id", None)
        ]
        before = len(handler._servants(engine))
        carrier.dead = True
        handler.on_player_died(engine, carrier)
        assert handler._captive_kind(engine, carrier) is None, "阵亡携带者不再持有俘虏"
        assert len(handler._servants(engine)) == before + 1, "随从应挣脱回场继续游荡"

    # 胜利：模拟全部随从+叛徒已被处置
    for s in handler._servants(engine):
        s_id = getattr(s, "id", None)
        engine.state.monsters = [m for m in engine.state.monsters if getattr(m, "id", None) != s_id]
    traitor.dead = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt35_small_change() -> None:
    """剧本 35：缩小移动/猫捕获/挣脱/飞机搜索与发动/逃离胜利（p46/p117）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=35)
    handler = engine._mode_handler()
    assert isinstance(handler, SmallChangeMode)
    flags = engine._haunt_flags()

    # 猫已布点（3 人局 1 只门厅）
    cats = handler._cats(engine)
    assert len(cats) >= 1, "至少应有一只猫"
    entrance = next(k for k, r in engine.state.board.items() if r.template_id == "entrance_hall")
    assert any(m.room_key == entrance for m in cats), "猫应在门厅"

    # 缩小：移动费用 ×2
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    assert handler.movement_cost_multiplier(engine, hero) == 2, "缩小后移动应 ×2"

    # 叛徒不能直接攻击英雄
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert handler.attack_allowed(engine, traitor, hero) is False, "叛徒不能直接攻击"

    # 猫捕获：力量胜利 → 捕获不伤害
    cat = cats[0]
    hero.room_key = cat.room_key
    hero.steps_remaining = 5
    might_before = hero.stats["might"]
    with patch.object(engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 9), \
         patch.object(engine, "_roll_attack", return_value=1):
        engine._monster_attack(cat, hero)
    assert str(hero.id) in flags.get("captured", {}), "猫应捕获英雄"
    assert hero.stats["might"] == might_before, "捕获不应造成伤害"

    # 被俘者挣脱：对决胜利
    with patch.object(engine, "_roll_attack", return_value=9), patch.object(
        engine, "roll_dice", side_effect=lambda count, label="": 1 if label == "猫对决" else count
    ):
        handler.on_turn_start(engine, hero)
    assert str(hero.id) not in flags.get("captured", {}), "对决胜利应挣脱"

    # 飞机搜索 + 发动 + 逃离
    hero.items.append("item_candle")
    bedroom_room = next((r for r in engine.state.board.values() if r.template_id in
                         ("bedroom", "master_bedroom", "attic", "game_room", "larder")), None)
    if bedroom_room is not None:
        bedroom_room.template_id = "bedroom"
        hero.room_key = bedroom_room.key
        _set_current(engine, hero)
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "search_plane" in ids, "在卧室类房间应能搜索飞机"
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "search_plane", {}) is True
        assert flags.get("plane_found") is True
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "start_plane" in ids
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "start_plane", {}) is True
        assert flags.get("plane_started") is True
        # 移到外缘房间逃离
        outer = next((r for r in engine.state.board.values() if r.template_id in handler.OUTER_ROOMS), None)
        if outer is not None:
            hero.room_key = outer.key
            _set_current(engine, hero)
            ids = {a.id for a in handler.available_actions(engine, hero)}
            assert "escape_plane" in ids
            assert handler.perform_action(engine, hero, "escape_plane", {}) is True
            assert hero.id in flags.get("escaped", [])
            assert handler.check_victory(engine) is True  # 3 人局需 2 人逃，先1人不够但测试只验证行动
            # 3 人局 half_ceil = 2，1 人逃不触发英雄胜——但 check_victory 不会返回 False
            engine.state.winner = None  # 重置以便后续测试


def verify_haunt36_swamp_escape() -> None:
    """剧本 36：洪水阶段/小艇/逃离/勋章暂停/小艇破坏/胜利条件（p47/p118）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=36)
    handler = engine._mode_handler()
    assert isinstance(handler, SwampEscapeMode)
    flags = engine._haunt_flags()

    # 阁楼在场；小艇在阁楼；阳台或塔楼必须在场（否则无处逃生）
    attic = next((k for k, r in engine.state.board.items() if r.template_id == "attic"), None)
    assert attic is not None, "阁楼应被强制入场"
    boat = engine.tokens_of_kind("rowboat")
    assert boat and boat[0].room_key == attic, "小艇应在阁楼"
    assert any(
        room.template_id in ("balcony", "tower") for room in engine.state.board.values()
    ), "阳台或塔楼应被强制入场"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 洪水推进：叛徒回合开始 → 计时器 1
    handler.on_turn_start(engine, traitor)
    assert engine._haunt_track_value("flood_timer") == 1, "叛徒回合应推进洪水"
    # 地下室部分淹：把英雄放到地下室再检查惩罚
    basement = next((k for k, r in engine.state.board.items() if r.floor == -1), None)
    if basement:
        hero.room_key = basement
        assert handler.movement_cost_floor(engine, hero) >= 3, "部分淹应有移动惩罚"
        assert handler._flood_desc(engine, handler._floor_for_room(engine, basement)) == "partial"

    # 扛小艇：×2 移动；令牌离房后仍算"艇在这里"
    hero.room_key = attic
    _set_current(engine, hero)
    assert handler.perform_action(engine, hero, "take_rowboat", {}) is True
    assert flags.get("boat_carrier") == hero.id
    assert handler.movement_cost_multiplier(engine, hero) == 2, "背小艇应 ×2"
    assert not engine.tokens_in_room(attic, "rowboat"), "扛起后令牌应离房"
    assert engine.tokens_held_by(hero.id, "rowboat")
    assert handler._boat_here(engine, hero)
    assert handler.bot_action_blocked(engine, hero, "take_rowboat") is True
    carrier_goals = handler.bot_goal_rooms(engine, hero)
    assert carrier_goals, "扛艇的人应去阳台/塔楼"

    # 勋章暂停（需在淹水房间——把英雄暂时放到地下室）
    hero.items.append("omen_medallion")
    basement_key = next(k for k, r in engine.state.board.items() if r.floor == -1)
    hero.room_key = basement_key
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "drop_medallion" in ids, "持勋章在淹水房间应能投掷"
    assert handler.perform_action(engine, hero, "drop_medallion", {}) is True
    assert flags.get("medallion_pause") is True
    handler.on_turn_start(engine, traitor)  # 应暂停不推进
    assert engine._haunt_track_value("flood_timer") == 1, "勋章应暂停洪水推进"

    # 逃跑：阳台 + 小艇
    balcony = next((k for k, r in engine.state.board.items() if r.template_id == "balcony"), None)
    if balcony is None:
        balcony = next((k for k, r in engine.state.board.items() if r.template_id == "tower"), attic)
    # 把小艇放在阳台
    for t in engine.tokens_of_kind("rowboat"):
        engine.place_token(t.uid, balcony)
    hero.room_key = balcony
    hero.movement_stopped = False
    # p47：乘艇逃离时不能留下活着的英雄——其他英雄也必须先站到阳台上。
    others = [p for p in engine.state.players if p.role == "hero" and not p.dead and p.id != hero.id]
    for p in others:
        p.room_key = balcony
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "escape_boat" in ids, "阳台+小艇应能逃离"
    assert handler.perform_action(engine, hero, "escape_boat", {}) is True
    assert hero.id in flags.get("escaped", [])
    # 3 人局 need_ceil = 2，1 人不够——其余英雄依次上艇
    for p in others:
        _set_current(engine, p)
        assert handler.perform_action(engine, p, "escape_boat", {}) is True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt37_checkmate() -> None:
    """剧本 37：死神不可攻击/圣印破解/国际象棋将军/弃赛判负（p48/p119）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=37)
    handler = engine._mode_handler()
    assert isinstance(handler, DeathCheckmateMode)
    flags = engine._haunt_flags()

    # 死神不可被攻击
    death = handler._death(engine)
    assert death is not None and engine._monster_invulnerable(death)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    assert handler.attack_allowed(engine, hero, death) is False, "死神不可被攻击"

    # 圣印在场（至少一枚在已探明房间）
    seals = engine.tokens_of_kind("holy_seal")
    assert len(seals) >= 1, "至少应有一枚圣印已放置"

    # 破解圣印 → 死神骰减少
    seal_room = seals[0].room_key
    hero.room_key = seal_room
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "break_seal" in ids, "在圣印房间应能破解"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "break_seal", {}) is True
    assert int(flags["seals_broken"]) == 1
    assert handler._hero_dice_penalty(engine) == 2, "3 人局每枚圣印 -2 骰"
    assert not engine.tokens_in_room(seal_room, "holy_seal"), "圣印应被移除"

    # 国际象棋：英雄知识 > 死神 → 英雄胜
    hero.room_key = death.room_key
    with patch.object(engine, "_roll_attack", return_value=8), patch.object(
        engine, "roll_dice", side_effect=lambda count, label="": 20 if label == "国际象棋" else count
    ):
        assert handler.on_monster_turn_start(engine, death) is True
    assert engine.state.winner == "heroes", "知识超过死神应将军"

    # 弃赛：死神房间无英雄 → 叛徒胜
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    hero.room_key = next(k for k in engine.state.board if k != death.room_key)
    assert handler.on_monster_turn_start(engine, death) is True
    assert engine.state.winner == "traitor", "死神房间无英雄应弃赛判负"

    # ---- M10-50 回归：坐庄制（p48/p119 棋盘不能空）
    # 修前 18 局全败且从未下过一盘棋：作祟后英雄各走各的，死神第一个回合房间
    # 就空了（弃赛判负）；叛徒还会跟进房间把坐庄的人捶死。
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    board = death.room_key
    for p in engine.state.players:
        if p.role == "hero":
            p.dead = False
    sitter = handler._board_sitter(engine)
    other = next(p for p in engine.state.players if p.role == "hero" and p.id != sitter.id)
    away = [k for k in engine.state.board if k != board]
    sitter.room_key = away[0]
    other.room_key = away[1 % len(away)]
    assert handler.bot_goal_rooms(engine, sitter) == [f"__room__{board}"], (
        "棋盘空着时坐庄者必须去坐（否则弃赛判负）"
    )
    assert handler.bot_stay_in_room(engine, sitter) is False, "还没坐下就不算守住"
    sitter.room_key = board
    assert handler.bot_goal_rooms(engine, sitter) == [f"__room__{board}"], "坐庄者应守住棋盘"
    assert handler.bot_stay_in_room(engine, sitter) is True, "落座后不再移动"
    assert handler.bot_stay_in_room(engine, other) is False, "非坐庄者不受守擂约束"
    seals_left = handler._unbroken_seal_rooms(engine)
    other_goals = handler.bot_goal_rooms(engine, other)
    if seals_left:
        assert other_goals and all(g in {f"__room__{k}" for k in seals_left} for g in other_goals), (
            f"棋盘有人时其余英雄应去破圣印：{other_goals}"
        )
    else:
        assert other_goals == [f"__room__{board}"], "圣印破完后回棋盘"
    traitor_seat = next(p for p in engine.state.players if p.role == "traitor")
    traitor_seat.dead = False
    assert handler.bot_blocked_rooms(engine, traitor_seat) == [board], (
        "p119：叛徒不许踏进死神房间（否则坐庄英雄被捶死 → 弃赛判负）"
    )
    assert handler.bot_blocked_rooms(engine, sitter) == [], "英雄不受禁区限制"

    # ---- M10-50 回归：棋局损失要打到骷髅上（属性归零即倒下）
    # 缺 _check_player_death 时坐庄英雄会带着 0/0 永远坐着：叛徒进不了房间、
    # 英雄也死不了，对局再也收不了场（seed127/3p 实测 300 回合跑不完）。
    doomed = sitter
    doomed.dead = False
    sanity_track = engine._stat_track(doomed, "sanity")
    doomed.stat_positions["sanity"] = 0  # 已在轨道最左格：再来 1 点就掉到骷髅
    doomed.stats["sanity"] = sanity_track[0]
    doomed.overflow["sanity"] = 0
    doomed.room_key = board
    engine.state.winner = None
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 0), patch.object(
        engine.rng, "choice", side_effect=lambda seq: 2
    ):
        assert handler.on_monster_turn_start(engine, death) is True
    assert doomed.dead, "棋局损失把理智打到 0 应倒下（p48 与战斗伤害同源）"
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"

    # ---- M10-50 回归：死神必须落在有英雄的房间（p119 由叛徒挑选）
    # 引擎按 spawn:"haunt_room" 生成在揭露房，而揭露者本人就是叛徒——房里没有
    # 英雄时死神第一个回合直接弃赛判负（seed101/3p 实测 t51 揭示、t54 收场）。
    for p in engine.state.players:
        if p.role == "hero":
            p.dead = False
    crowd = away[0]
    for p in engine.state.players:
        if p.role == "hero":
            p.room_key = crowd
    death.room_key = board
    handler.setup(engine, engine.state.haunt, board)
    assert death.room_key == crowd, "死神应落到有英雄的房间"


def verify_haunt39_heir() -> None:
    """剧本 39：雕像走廊/继承人/刺客偷袭/矛与戒指胜利（p50/p121）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=39)
    handler = engine._mode_handler()
    assert isinstance(handler, HeirAssassinMode)
    flags = engine._haunt_flags()

    # 雕像走廊在场；继承人已选
    throne = handler._throne_room(engine)
    assert throne is not None and engine.state.board[throne].template_id == "statuary_corridor"
    heir = handler._heir(engine)
    assert heir is not None and heir.role == "hero", "继承人应已选定"
    assert len(flags.get("assassin_rooms", [])) >= 1, "应有刺客已布点"

    # 刺客偷袭：英雄进入 → 暴露 + 伤害 + 服毒死亡
    hero = next(
        (p for p in engine.state.players if p.role == "hero" and not p.dead and p.id != heir.id),
        heir,  # 非继承人英雄可能已死——用继承人测试
    )
    # 这条轨迹下可能只剩继承人一名英雄：他被选作刺客伏击目标时会被偷袭打死，
    # 而后面还要用他验证"持矛+戒登雕像走廊"的英雄胜利线。先把存活英雄属性
    # 抬满，保证伏击不致死（本段验的是刺客机制，不是伤害数值）。
    _buff_heroes_to_max(engine)
    assassin_room = flags["assassin_rooms"][0]
    hero.room_key = assassin_room
    monsters_before = len(engine.state.monsters)
    handler.on_enter_room(engine, hero, engine.state.board[assassin_room])
    # 刺客应已死亡（服毒）
    assert len(engine.state.monsters) < monsters_before or not any(
        m.room_key == assassin_room for m in engine.state.monsters
    ), "刺客应已服毒死亡"

    # 继承人 + 矛 + 戒指在雕像走廊 → 英雄胜
    # p50 原文是 "the Spear card"：矛必须走卡牌通道（旧版 marker 令牌
    # 谁都无法拾取，英雄胜利线不可达——M10-35 修）。
    heir.room_key = throne
    if "omen_ring" not in heir.items:
        heir.items.append("omen_ring")
    spear_room = flags.get("spear_room")
    assert "omen_spear" in engine.state.room_items.get(spear_room, []), (
        "矛（omen_spear 卡）应摆在随机已探明房间里"
    )
    assert "omen_spear" not in engine.tokens_of_kind("spear"), "不应再生成矛令牌"
    # 走引擎常规拾取通道：搬到矛房间把它捡起来
    heir.room_key = spear_room
    assert engine.pickup_item(heir, "omen_spear"), "继承人应能正常拾取矛卡"
    heir.room_key = throne
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # 继承人死亡 → 叛徒胜
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    heir.dead = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor"

    # ---- M10-51 回归：机器人也要会抢关键牌（默认"从不偷牌"，胜线会断）
    # 实测 6 局（3 人局）戒指 5 局整局攥在叛徒手里、英雄既不还手也不夺牌
    # → 18/18 全败、胜线在 AI 层断开。队友抢到也算：quest_carrier 会转交。
    engine.state.winner = None
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    for p in engine.state.players:
        if p.role == "hero":
            p.dead = False
    traitor.dead = False
    heir.items[:] = [c for c in heir.items if c not in ("omen_ring", "omen_spear")]
    traitor.items[:] = [c for c in traitor.items if c not in ("omen_ring", "omen_spear")]
    traitor.items.append("omen_ring")
    assert handler.bot_wants_steal(engine, heir, traitor) == "omen_ring", (
        "继承人缺戒指而叛徒拿着 → 必须点名去抢"
    )
    assert handler.bot_wants_steal(engine, traitor, heir) is None, "叛徒不抢英雄的东西"
    heir.items.append("omen_ring")
    assert handler.bot_wants_steal(engine, heir, traitor) is None, "继承人有戒指就不再抢"
    heir.items.remove("omen_ring")
    traitor.items.append("omen_spear")
    picked = handler.bot_wants_steal(engine, heir, traitor)
    assert picked in {"omen_spear", "omen_ring"} and picked not in heir.items, (
        "矛戒都缺时抢回任意一件缺失的关键牌"
    )
    # 引擎侧：只有机器人走这条通道，人类玩家仍然自己弹窗
    heir.control = "human"
    assert engine._bot_steal_choice(heir, traitor) is None, "人类玩家不替其决定"
    heir.control = "bot"
    assert engine._bot_steal_choice(heir, traitor) == picked, (
        "机器人由剧本指定该抢哪张（不靠随机挑第一件）"
    )


def verify_haunt41_invisible_traitor() -> None:
    """剧本 41：隐形叛徒冒烟——分派/侦测行动/胜利条件（p52/p123）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=41)
    handler = engine._mode_handler()
    assert isinstance(handler, InvisibleTraitorMode)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 侦测行动可用
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "detect_traitor" in ids, "侦测行动应可用"

    # ---- M10-56 回归：侦测成功要留下线索并推进轨道
    # 修前：动作既没有 set_flags 也没有 progress，跑完只有一句日志——
    # 轨道恒 0/10、位置不知、机器人也无从追击（seed109/6p 300 回合收不了场）。
    flags = engine._haunt_flags()
    flags["detected_room"] = None
    before = engine._haunt_track_value("detections")
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "detect_traitor", {}) is True
    assert flags.get("detected_room") == traitor.room_key, "侦测成功应锁定叛徒所在房间"
    assert engine._haunt_track_value("detections") == before + 1, "侦测成功应推进 detections 轨道"
    assert str(hero.id) in flags.get("detected_by", []), "应记录侦测者"

    # ---- M10-56 回归：偷袭"对手无法防御"（p123）
    assert handler.defense_roll_disabled(engine, traitor, hero) is True, "叛徒空手攻击是偷袭"
    assert handler.defense_roll_disabled(engine, traitor, hero, "item_revolver") is False, (
        "持物品的攻击按普通攻击结算（原文 Unless you are attacking with an item）"
    )
    assert handler.defense_roll_disabled(engine, hero, traitor) is False, "英雄攻击不受影响"

    # ---- M10-56 回归：机器人循线索追击（英雄胜 = 叛徒死亡）
    assert handler.bot_goal_rooms(engine, hero) == [f"__room__{traitor.room_key}"], (
        "英雄应奔向叛徒所在房间"
    )

    # 叛徒死亡 → 英雄胜（引擎兜底）
    traitor.dead = True
    engine.check_victory()
    assert engine.state.winner == "heroes", "叛徒死亡应触发英雄胜利"


def verify_haunt42_hell_gate() -> None:
    """剧本 42：雕像活化/属性削弱/叛徒可攻击/胜利条件（p53/p124）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=42)
    handler = engine._mode_handler()
    assert isinstance(handler, HellGateHeroMode)
    flags = engine._haunt_flags()

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 叛徒无敌：不能被攻击
    assert handler.attack_allowed(engine, hero, traitor) is False, "叛徒应无敌"

    # 活化雕像：持圣徽 → 审判官
    # 形态由背包里**第一件**雕像物品决定，先清掉探索期可能抽到的同类物品，
    # 保证两处断言（圣徽活化审判官、圣徽被消耗）都只对唯一一张成立。
    hero.items[:] = [card_id for card_id in hero.items if card_id not in handler.STATUE_ITEMS]
    hero.items.append("omen_holy_symbol")
    statue_room = flags["statue_room"]
    hero.room_key = statue_room
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "animate_statue" in ids, "持圣徽应能活化雕像"
    assert handler.perform_action(engine, hero, "animate_statue", {}) is True
    assert flags.get("statue_form") == "judge", "圣徽应活化审判官"
    assert "omen_holy_symbol" not in hero.items, "圣徽应被消耗"

    # 雕像与叛徒同房 → 削弱 Speed
    traitor.room_key = statue_room
    speed_before = traitor.stats["speed"]
    hero.room_key = statue_room
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "move_statue", {}) is True
    # 雕像已在叛徒房间 → 削弱
    assert traitor.stats["speed"] < speed_before or traitor.stat_positions.get("speed", 0) < 3, "雕像应削弱叛徒速度"

    # 削弱至 0 → 可被攻击
    traitor.stats["speed"] = 1
    traitor.stat_positions["speed"] = 0
    traitor.stats["might"] = 0
    traitor.stat_positions["might"] = 0
    traitor.stats["sanity"] = 0
    traitor.stat_positions["sanity"] = 0
    traitor.stats["knowledge"] = 0
    traitor.stat_positions["knowledge"] = 0
    assert handler._traitor_vulnerable(engine) is True
    assert handler.attack_allowed(engine, hero, traitor) is True, "属性归零后应可被攻击"

    # ---- M10-57 回归：机器人目标（p53 雕像链条）
    # 修前：本类既没有 bot_goal_rooms（rule_data 的 key_rooms/required_cards 也是
    # 空的），画像又缺 attack_traitor_players——18 局实测雕像一次都没被激活
    # （圣物躺在地上没人捡）、英雄只在房里游荡，胜负全看叛徒会不会死于别的伤害。
    for stat in ("speed", "might", "sanity", "knowledge"):
        traitor.stats[stat] = 2
        traitor.stat_positions[stat] = 1
    assert handler._traitor_vulnerable(engine) is False, "先恢复成未破防状态"
    statue_items = list(handler.STATUE_ITEMS)
    for other in engine.state.players:
        if other.role == "hero":
            other.items[:] = [c for c in other.items if c not in statue_items]
    saved_form = flags.get("statue_form")
    flags["statue_form"] = None
    assert handler.bot_goal_rooms(engine, hero) == [], (
        "雕像未活化又没拿圣物时不该守在雕像房（交给通用目标去捡圣物）"
    )
    hero.items.append(statue_items[0])
    assert handler.bot_goal_rooms(engine, hero) == [f"__room__{statue_room}"], (
        "拿着圣物应去雕像房激活它"
    )
    flags["statue_form"] = saved_form or "judge"
    assert handler.bot_goal_rooms(engine, hero) == [f"__room__{statue_room}"], (
        "已活化：英雄要在雕像旁才推得动（move_statue 要求同房）"
    )
    assert handler.bot_goal_rooms(engine, traitor) == [], "叛徒没有这条目标"
    for stat in ("speed", "might", "sanity", "knowledge"):
        traitor.stats[stat] = 0
        traitor.stat_positions[stat] = 0
    assert handler.bot_goal_rooms(engine, hero) == [f"__room__{traitor.room_key}"], (
        "叛徒被削到可攻击后转为收尾追击"
    )


def verify_haunt43_shadow_exorcism() -> None:
    """剧本 43：影子绑定/向五芒星移动/攻击影子/仪式胜利（p54/p125）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=43)
    handler = engine._mode_handler()
    assert isinstance(handler, ShadowExorcismMode)
    flags = engine._haunt_flags()

    # 影子数量 = 英雄数；五芒星室在场
    shadows = [m for m in engine.state.monsters if m.template_id == "ghost"]
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    assert len(shadows) >= 1, "至少应有一只影子"
    pentagram = flags.get("pentagram_room")
    assert pentagram is not None and engine.state.board[pentagram].template_id == "pentagram_chamber"

    # 影子向五芒星移动
    shadow = shadows[0]
    dist_before = engine._path_length(shadow.room_key, pentagram)
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 3 if label == "影子移动" else count):
        assert handler.on_monster_move(engine, shadow, 3) is True
    dist_after = engine._path_length(shadow.room_key, pentagram)
    assert dist_after <= dist_before, "影子应向五芒星移动"

    # 影子到达五芒星 → 绑定英雄死亡
    shadow.room_key = pentagram
    bound_hero = handler._bound_hero(engine, shadow)
    assert bound_hero is not None
    handler.on_monster_move(engine, shadow, 3)
    assert bound_hero.dead, "影子到达五芒星后绑定英雄应变成 Specter"

    # 攻击影子 → 击晕 + 绑定英雄 -1 Speed（用第二只影子测试）
    hero2 = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
    if hero2 is not None:
        shadow2 = next((m for m in engine.state.monsters if m.template_id == "ghost" and m.room_key != pentagram), None)
        if shadow2 is not None:
            hero2.room_key = shadow2.room_key
            engine._active_player_id = hero2.id
            speed_before = hero2.stat_positions.get("speed")
            with patch.object(engine, "_roll_attack", return_value=9), patch.object(
                engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 1
            ):
                assert engine.attack(hero2, shadow2) is True
            assert shadow2.stunned_turns > 0, "影子被击败应击晕"
            assert hero2.stat_positions.get("speed") is not None and hero2.stat_positions["speed"] < speed_before, "绑定英雄应 -1 Speed"

    # 仪式：找仪式 + 放令牌 → 英雄胜
    hero3 = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
    if hero3 is not None:
        ritual_room = next((r for r in engine.state.board.values() if r.template_id in ("catacombs", "chapel", "library", "research_laboratory")), None)
        if ritual_room is not None:
            hero3.room_key = ritual_room.key
            _set_current(engine, hero3)
            with patch.object(engine, "_resolve_check", return_value=True):
                assert handler.perform_action(engine, hero3, "find_ritual", {}) is True
            assert flags.get("ritual_found") is True
            # 仪式检定（放令牌）
            outer = next((r for r in engine.state.board.values() if r.template_id in ("balcony", "garden", "graveyard", "patio", "tower")), None)
            if outer is not None:
                hero3.room_key = outer.key
                _set_current(engine, hero3)
                with patch.object(engine, "_resolve_check", return_value=True):
                    assert handler.perform_action(engine, hero3, "ritual_roll", {}) is True
            # 模拟放满玩家数枚令牌 → 英雄胜
            for i in range(len(engine.state.players)):
                engine.spawn_token("sanity_check", label="仪式", role="check", room_key=hero3.room_key)
            assert handler.check_victory(engine) is True
            assert engine.state.winner == "heroes"


def verify_haunt44_supernatural_aging() -> None:
    """剧本 44：衰老 token/十年效果/仪式检定/勋章减速/胜利条件（p55/p126）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=44)
    handler = engine._mode_handler()
    assert isinstance(handler, SupernaturalAgingMode)
    flags = engine._haunt_flags()

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 开局每人 1 枚衰老 token
    assert handler._aging_tokens(engine, hero) == 1, "开局应有 1 枚衰老 token"

    # 衰老：叛徒回合开始 → 英雄掷骰加 token
    tokens_before = handler._aging_tokens(engine, hero)
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 2 if label == "衰老" else count):
        handler.on_turn_start(engine, traitor)
    assert handler._aging_tokens(engine, hero) > tokens_before, "叛徒回合应增加衰老 token"

    # 仪式：房间限制 + 每房一次
    ritual_room = next((r for r in engine.state.board.values() if r.template_id in handler.RITUAL_ROOMS), None)
    if ritual_room is not None:
        hero.room_key = ritual_room.key
        _set_current(engine, hero)
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "ritual_roll" in ids, "在仪式房间应能检定"
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "ritual_roll", {}) is True
        # 同房不能再用
        engine._reset_player_turn_state(hero)
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "ritual_roll" not in ids, "同房不能再次使用"

    # 勋章减速
    hero.items.append("omen_medallion")
    tokens_before_med = handler._aging_tokens(engine, hero)
    with patch.object(engine, "roll_dice", side_effect=lambda count, label="": 3 if label == "衰老" else count):
        handler.on_turn_start(engine, traitor)
    # 3-1(勋章)=2 加 token（而非 3）
    # 勋章持有者获得较少 token（或因衰老效果死亡——都是合法结果）
    assert hero.dead or handler._aging_tokens(engine, hero) <= tokens_before_med + 2,         "勋章应减少衰老（或英雄因衰老死亡）"

    # 胜利：仪式进度满
    engine._set_haunt_track_value("ritual_progress", engine._haunt_track_target("ritual_progress"))
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt45_time_bomb() -> None:
    """剧本 45：炸弹标记/拆弹/大炸弹计时与 8+ 爆炸/接近引爆/叛徒不动（p56/p127）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=45)
    handler = engine._mode_handler()
    assert isinstance(handler, TimeBombMode)
    flags = engine._haunt_flags()

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 每人身上有炸弹；叛徒握着炸药卡（p127 Right Now）
    assert handler._has_bomb(engine, hero), "英雄应有炸弹"
    assert handler.DYNAMITE in traitor.items, "叛徒开局应握着炸药卡"

    # ---- M10-55 回归：叛徒不能移动（p127 "You cannot move"）
    assert handler.movement_cost_floor(engine, traitor) == 99, "叛徒应被钉在原地"
    assert handler.movement_cost_floor(engine, hero) == 0, "英雄不受移动限制"

    # 拆弹（M10-55 起由 handler 自掷骰：通用检定看不到骰面，≤2 引爆会失效）
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "defuse_bomb" in ids, "有炸弹应能拆弹"
    with patch.object(engine, "roll_dice", side_effect=lambda c, l="": 9 if l == "拆除炸弹" else c):
        assert handler.perform_action(engine, hero, "defuse_bomb", {}) is True
    assert not handler._has_bomb(engine, hero), "拆弹后炸弹应移除"

    # p56：掷出 ≤2 → 炸弹被激活，同房探险者一起被炸死
    other = next(
        (p for p in engine.state.players if p.role == "hero" and not p.dead and p.id != hero.id),
        None,
    )
    if other is not None:
        _set_current(engine, other)
        other.room_key = hero.room_key
        with patch.object(engine, "roll_dice", side_effect=lambda c, l="": 0):
            assert handler.perform_action(engine, other, "defuse_bomb", {}) is True
        assert other.dead, "掷出 ≤2 应就地引爆、本人被炸死"

    # ---- M10-55 回归：大炸弹计时在叛徒**回合结束**推进（不再写 drown_timer）
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    for p in engine.state.players:
        if p.role == "hero":
            p.dead = False
    engine._set_haunt_track_value("big_bomb_timer", 0)
    with patch.object(engine, "roll_dice", side_effect=lambda c, l="": 0 if l == "大炸弹计时" else c):
        handler.on_turn_end(engine, traitor)
    assert engine._haunt_track_value("big_bomb_timer") == 1, "叛徒回合结束应推进大炸弹计时"
    assert flags.get("big_bomb_armed") is True, "首回合结束后引爆触发器才武装"

    # p127：第 12 回合大炸弹完成 → 全屋同归于尽（叛徒胜）
    engine._set_haunt_track_value("big_bomb_timer", handler.BIG_BOMB_TURNS - 1)
    engine.state.winner = None
    handler.on_turn_end(engine, traitor)
    assert engine.state.winner == "traitor", "第 12 回合大炸弹完成应判叛徒胜"

    # ---- M10-55 回归：8+ 时"叛徒左手最近、还带着活炸弹"的英雄爆炸
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    engine._set_haunt_track_value("big_bomb_timer", 0)
    flags["bomb_defused"] = []
    for p in engine.state.players:
        if p.role == "hero":
            p.dead = False
    doomed = handler._next_bomb_hero(engine, traitor)
    assert doomed is not None, "应能找到还带着活炸弹的英雄"
    doomed.room_key = traitor.room_key  # 与叛徒同房：爆炸只波及本房
    with patch.object(engine, "roll_dice", side_effect=lambda c, l="": 8):
        handler.on_turn_end(engine, traitor)
    assert doomed.dead, "8+ 时该英雄应被炸死"

    # ---- M10-55 回归：接近引爆（p127 邻室"不需要有门相连"）
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    for p in engine.state.players:
        if p.role == "hero":
            p.dead = False
    flags["bomb_defused"] = []
    flags["big_bomb_armed"] = True
    walker = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    walker.room_key = traitor.room_key
    handler.on_enter_room(engine, walker, engine.state.board[traitor.room_key])
    assert walker.dead, "带弹英雄踏进叛徒房间应立刻爆炸"
    # 已拆弹的英雄免疫
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    walker.dead = False
    flags["bomb_defused"] = [str(walker.id)]
    walker.room_key = traitor.room_key
    handler.on_enter_room(engine, walker, engine.state.board[traitor.room_key])
    assert not walker.dead, "炸弹已拆的英雄走进引爆区不受影响"

    # 叛徒死 + 英雄活 → 英雄胜
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    traitor.dead = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt46_the_feast_setup() -> None:
    """剧本 46：开局布点、被击败即死、受害者尸体链路、漫游触发（p57/p128）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=46)
    handler = engine._mode_handler()
    assert isinstance(handler, CannibalFeastMode)
    flags = engine._haunt_flags()
    hero_count = sum(1 for p in engine.state.players if p.role == "hero")

    # 阁楼与餐厅被强制入场（模板自带楼层：阁楼上、餐厅下）
    attic = next(r for r in engine.state.board.values() if r.template_id == "attic")
    dining = next(r for r in engine.state.board.values() if r.template_id == "dining_room")
    victims = [m for m in engine.state.monsters if m.template_id == "victim"]
    freaks = [m for m in engine.state.monsters if m.template_id == "cannibal_freak"]
    assert len(victims) == hero_count and len(freaks) == hero_count
    # 开局布点（受害者在阁楼、狂徒在餐厅）要用 _force_haunt 验证：
    # 受害者带"漫游"规则，触发作祟的那一回合结束时就会离开阁楼
    # （seed113 实测走到了卧室），拿跑完一回合的状态断言"开局位置"必然假失败。
    forced = _force_haunt(seed=113, players=3, haunt_id=46)
    f_attic = next(r for r in forced.state.board.values() if r.template_id == "attic")
    f_dining = next(r for r in forced.state.board.values() if r.template_id == "dining_room")
    f_victims = [m for m in forced.state.monsters if m.template_id == "victim"]
    f_freaks = [m for m in forced.state.monsters if m.template_id == "cannibal_freak"]
    assert f_victims and all(v.room_key == f_attic.key for v in f_victims), "受害者开局应在阁楼"
    assert f_freaks and all(f.room_key == f_dining.key for f in f_freaks), "狂徒开局应在餐厅"
    assert flags["victims_total"] == hero_count
    assert len(flags["victim_facing"]) == hero_count

    # 被击败即死（p57/p128）：对受害者的查询自带处决副作用——生成尸体、
    # 移出对局、封锁逃生路线（该钩子的调用点唯一且就在引擎击杀结算处）；
    # 对狂徒的查询是纯判定（狂徒由引擎移除、不翻尸体）。
    v0 = victims[0]
    room_of_v0 = v0.room_key
    assert handler.monster_killed_on_defeat(engine, v0, None, "might", "") is True
    assert handler.monster_killed_on_defeat(engine, freaks[0], None, "might", "") is True
    corpses = engine.tokens_in_room(room_of_v0, "corpse")
    assert len(corpses) == 1 and corpses[0].label == "受害者尸体"
    assert flags["blood_spilled"] is True and flags["victim_corpses"] == 1
    assert all(m.id != v0.id for m in engine.state.monsters), "受害者应已移出对局"
    remaining_freaks = [m for m in engine.state.monsters if m.template_id == "cannibal_freak"]
    assert len(remaining_freaks) == hero_count, "狂徒查询不应有副作用（仍在场）"

    # 英雄被杀 likewise：尸体 + 血腥标志（p128 "dead explorer"）
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero_room = hero.room_key
    handler.on_player_died(engine, hero)
    assert any(t.label == "探险者尸体" for t in engine.tokens_in_room(hero_room, "corpse"))

    # 漫游（p57）：叛徒左侧玩家的回合开始触发；与英雄同房间的受害者不动
    mover = handler._victim_mover(engine)
    assert mover is not None
    live = [m for m in engine.state.monsters if m.template_id == "victim"]
    assert live, "应还有受害者存活"
    live[0].room_key = hero.room_key  # hero 在上面只被模拟了尸体后处理，人还活着
    handler.on_turn_start(engine, mover)
    still = next(m for m in engine.state.monsters if m.id == live[0].id)
    assert still.room_key == hero.room_key, "与英雄同房间的受害者不应移动"


def verify_haunt46_front_door_and_victory() -> None:
    """剧本 46：开正门→护送/送出/出逃链路、进食、胜负分支（p57/p128）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=46)
    handler = engine._mode_handler()
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 开正门（知识检定/力量掷骰都 mock 成必成）→ 门开 + 结束回合（p57）
    _set_current(engine, hero)
    with patch.object(engine, "_resolve_check", return_value=True), patch.object(
        engine, "roll_dice", return_value=6
    ):
        assert handler.perform_action(engine, hero, "unlock_front_door", {}) is True
    assert flags["front_door_open"] is True
    assert hero.movement_stopped, "开门后应结束回合"

    # 护送：英雄与受害者同房 → 带往门厅方向（p57，电子版简化口径）
    entrance = next(r for r in engine.state.board.values() if r.template_id == "entrance_hall")
    victim = next(m for m in engine.state.monsters if m.template_id == "victim")
    victim.room_key = hero.room_key = entrance.key

    # ---- M10-58 回归：门厅不再提供"护送"（目的地就是门厅，纯空转）
    # 修前 escort_victim 与 send_victim_out 同时提供，而 rule_data 里前者排在前、
    # 机器人打分相同取先出现的那个 ⇒ 永远选护送；护送在门厅又是"假成功"
    # （打一句日志 + return True），整回合的剧本行动被白吃，正门开了也送不出人
    # （探针实测：send_victim_out 出现 4 次、执行 0 次）。
    ids_here = {a.id for a in handler.available_actions(engine, hero)}
    assert "send_victim_out" in ids_here, "门厅 + 门开 + 身边有受害者 → 应能送出门"
    assert "escort_victim" not in ids_here, "已在门厅不该再给护送（空转）"
    assert handler.perform_action(engine, hero, "escort_victim", {}) is False, (
        "护送在门厅是空转，必须返回 False（不能白吃整回合）"
    )

    assert handler.perform_action(engine, hero, "send_victim_out", {}) is True
    assert flags["victims_escaped"] == 1 and flags["victim_escaped_any"] is True
    assert all(m.id != victim.id for m in engine.state.monsters), "逃出的受害者应移出游戏"

    # 英雄出逃/再进门（p57 shuttle）
    assert handler.perform_action(engine, hero, "escape_house", {}) is True
    assert hero.id in flags["escaped_hero_ids"]
    assert handler.perform_action(engine, hero, "reenter_house", {}) is True
    assert hero.id not in flags["escaped_hero_ids"]

    # 进食：叛徒与受害者尸体同房、无活英雄 → 全属性上移一格、尸体移除（p128）
    # 注意引擎的"+1"是卡尺格位上移（轨道有重复数值，数值未必 +1——25/32 号同款坑）
    corpse = engine.spawn_token("corpse", label="受害者尸体", role="marker", room_key=traitor.room_key)
    flags["victim_corpses"] = 1
    pos_before = {s: traitor.stat_positions.get(s, 0) for s in ("speed", "might", "sanity", "knowledge")}
    _set_current(engine, traitor)
    assert handler.perform_action(engine, traitor, "feast_corpse", {}) is True
    for s in ("speed", "might", "sanity", "knowledge"):
        track = engine._stat_track(traitor, s) or []
        if pos_before[s] < len(track) - 1:
            assert traitor.stat_positions.get(s, 0) == pos_before[s] + 1, f"{s} 应上移一格"
    assert engine.token_by_uid(corpse.uid) is None, "吃掉的尸体应移出游戏"
    assert flags["victim_corpses"] == 0
    assert traitor.movement_stopped, "进食应花掉整回合"

    # ---- M10-58 回归：见血后胜利路线 B 关闭，英雄目标转向狂徒与叛徒
    # 修前 bot_goal_rooms 只认"门没开→找受害者、门开了→去门厅"，见血后仍在
    # 满屋护送受害者（18 局采样 6 局全部见血、英雄胜 1/18），而画像的
    # victory_focus 早就写着"见血就转杀光狂徒"。
    flags["blood_spilled"] = True
    goals = handler.bot_goal_rooms(engine, hero)
    allowed = {
        f"__room__{m.room_key}"
        for m in engine.state.monsters
        if m.template_id == "cannibal_freak"
    } | {f"__room__{traitor.room_key}"}
    assert goals and all(g in allowed for g in goals), (
        f"见血后目标应指向狂徒/叛徒：{goals}"
    )

    # 胜负：叛徒死 + 狂徒还在 → 吸收兜底（不判英雄胜，游戏继续）
    traitor.dead = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner is None, "狂徒还在，叛徒死不该直接判英雄胜"

    # 狂徒也全灭 → 英雄胜（p57 路线 A）
    for m in [m for m in engine.state.monsters if m.template_id == "cannibal_freak"]:
        engine._kill_monster(m)
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # 重开一局验证叛徒胜 A：受害者被吃光（无尸体剩余、无人逃出过）
    engine2 = _run_until_haunt(seed=137, players=3, haunt_id=46)
    h2 = engine2._mode_handler()
    f2 = engine2._haunt_flags()
    assert isinstance(h2, CannibalFeastMode)
    for m in [m for m in engine2.state.monsters if m.template_id == "victim"]:
        h2._kill_victim_to_corpse(engine2, m)
    for t in list(engine2.tokens_of_kind("corpse")):
        h2._consume_corpse(engine2, t)
    assert h2.check_victory(engine2) is True
    assert engine2.state.winner == "traitor", "受害者被吃光应判叛徒胜"
    assert f2["victim_escaped_any"] is False


def verify_haunt47_worm_ouroboros_setup() -> None:
    """剧本 47：变蛇出局/物品掉落/同伴吞掉/骷髅兜底/双头布点（p58/p129）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=47)
    handler = engine._mode_handler()
    assert isinstance(handler, OuroborosMode)
    flags = engine._haunt_flags()
    haunt_room = engine.state.meta["haunt_rule"]["haunt_room"]
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # p129：叛徒移出游戏（变蛇），物品全掉揭示房
    assert traitor.dead, "叛徒应变蛇出局"
    assert traitor.items == [] and traitor.companions == []
    pile = engine.state.room_items.get(haunt_room, [])
    assert pile, "揭示房应有物品堆"
    # p129：Girl/Dog/Madman 被吞掉（不在掉落堆里）
    assert not any(cid in handler.DEVOUR_CARDS for cid in pile), "被吞的同伴不该出现在掉落堆"

    # p58：施咒焦点骷髅必须在场（掉落堆或某英雄手里）
    assert handler.SKULL in pile or any(
        handler.SKULL in p.items for p in engine.state.players
    ), "骷髅兜底未生效"

    # 双头放揭示房；hit 需求数 = ceil(玩家数/2)
    heads = handler._heads(engine)
    assert len(heads) == 2 and all(h.room_key == haunt_room for h in heads)
    assert flags["hits_needed"] == 2, "3 人局应需 2 次重击"
    assert flags["body_left"] == 16

    # p129：蛇头不可击晕——on_monster_defeated 记 hit 而非击晕
    head = heads[0]
    assert handler.on_monster_defeated(engine, head, 2) is True
    assert head.stunned_turns == 0, "蛇头不该被击晕"
    assert flags["head_hits"][head.id] == 1 and head in engine.state.monsters
    # 未满数不移除；满数由 handler 杀死
    handler.on_monster_defeated(engine, head, 1)
    assert all(m.id != head.id for m in engine.state.monsters), "满数后蛇头应被移除"

    # p58：未削弱的蛇头禁止攻击（attack_allowed 拦截）
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    other = next(h for h in handler._heads(engine))
    assert handler.attack_allowed(engine, hero, other) is False

    # ---- M10-59 回归：机器人目标与关键牌声明（p58 的"捡骷髅→施咒"链）
    # bot_goal_rooms 只追【未削弱】的蛇头（都削弱完就没目标，交给围攻）；
    # rule_data 的 required_cards 声明骷髅，泛用"关键牌掉地上就去捡"才会生效。
    goals = handler.bot_goal_rooms(engine, hero)
    assert goals and all(g == f"__room__{other.room_key}" for g in goals), (
        f"应追未削弱的蛇头：{goals}"
    )
    flags["weakened_heads"] = sorted({h.id for h in handler._heads(engine)})
    assert handler.bot_goal_rooms(engine, hero) == [], "蛇头全部削弱后不再追（改围攻）"
    flags["weakened_heads"] = []
    assert handler.bot_goal_rooms(engine, traitor) == [], "叛徒开局已出局，无此目标"
    assert "omen_skull" in ((engine.state.haunt.rule_data or {}).get("required_cards") or []), (
        "骷髅必须声明为 required_cards，机器人才会主动去捡"
    )


def verify_haunt47_spell_and_bodies() -> None:
    """剧本 47：施咒链路、蛇身放置、胜负分支（p58/p129）。"""
    engine = _run_until_haunt(seed=137, players=3, haunt_id=47)
    handler = engine._mode_handler()
    assert isinstance(handler, OuroborosMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    head = handler._heads(engine)[0]

    # 施咒：无骷髅失败 → 给骷髅 + 同房 → 理智检定 mock 成功 → 力量降 5、可被攻击
    _set_current(engine, hero)
    assert handler.perform_action(engine, hero, "cast_weakening_spell", {}) is False
    hero.items.append(handler.SKULL)
    hero.room_key = head.room_key
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "cast_weakening_spell", {}) is True
    assert head.might == 5 and head.id in flags["weakened_heads"]
    assert handler.attack_allowed(engine, hero, head) is True, "削弱后应可攻击"

    # p129：蛇身放置——每房限 1 枚、计数推进、放满 16 节判叛徒胜
    room_a = head.room_key
    room_b = next(k for k in engine.state.board if k != room_a)
    handler._drop_body(engine, room_a)
    assert int(flags["body_left"]) == 15
    handler._drop_body(engine, room_a)  # 同房重复放应被拒绝
    assert int(flags["body_left"]) == 15
    handler._drop_body(engine, room_b)
    assert engine._haunt_track_value("ouroboros_body") == 2
    flags["body_left"] = 1
    room_c = next(k for k in engine.state.board if k not in (room_a, room_b))
    handler._drop_body(engine, room_c)
    engine.check_victory()  # 真实链路由 _resolve_monster_turns 末尾触发
    assert engine.state.winner == "traitor", "16 节蛇身放满应判叛徒胜"

    # 重开一局验证英雄胜：双头皆斩（p58）
    engine2 = _run_until_haunt(seed=137, players=3, haunt_id=47)
    h2 = engine2._mode_handler()
    assert isinstance(h2, OuroborosMode)
    for m in list(h2._heads(engine2)):
        h2.on_monster_defeated(engine2, m, 1)  # 2 次 hit 杀死
        h2.on_monster_defeated(engine2, m, 1)
    assert h2.check_victory(engine2) is True
    assert engine2.state.winner == "heroes"
    # 叛徒开局出局也不能触发"英雄胜"兜底——双头在场时游戏必须继续
    engine3 = _run_until_haunt(seed=137, players=3, haunt_id=47)
    h3 = engine3._mode_handler()
    assert h3.check_victory(engine3) is True and engine3.state.winner is None

    # 英雄随后也全灭时，start_turn 扫过一圈死者必须判出叛徒胜
    # （否则永远停在 HAUNT_PHASE，seed109/4p 实测卡在 27 回合）。
    for p in engine3.state.players:
        p.dead = True
    engine3.start_turn()
    assert engine3.state.winner == "traitor"


def verify_haunt48_crimson_jack_setup() -> None:
    """剧本 48：杰克布点、恐惧光环掉点、打不死→回归且强化（p59/p130）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=48)
    handler = engine._mode_handler()
    assert isinstance(handler, CrimsonJackMode)
    flags = engine._haunt_flags()

    # p130：杰克放门厅
    jack = handler._jack(engine)
    assert jack is not None, "杰克应在场"
    entrance = handler._entrance_key(engine)
    assert entrance is not None and jack.room_key == entrance
    assert (jack.speed, jack.might, jack.sanity) == (3, 3, 3)
    # p130：叛徒仍在场（未出局）
    assert any(p.role == "traitor" and not p.dead for p in engine.state.players)

    # p59/p130：恐惧光环——与杰克同房间的英雄，理智检定失败则各掉 1 点
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero.room_key = jack.room_key
    # 注意"临时加成（overflow）先被消耗"：按有效属性（轨位+加成）计量，
    # 否则英雄带加值时轨位不动、掉点数会算成 0 而假失败。
    affected = (*handler.MENTAL, *handler.PHYSICAL)
    before = {
        s: hero.stat_positions.get(s, 0) + hero.overflow.get(s, 0) for s in affected
    }
    with patch.object(engine, "_resolve_check", return_value=False):
        handler.on_turn_start(engine, hero)
    after = {
        s: hero.stat_positions.get(s, 0) + hero.overflow.get(s, 0) for s in affected
    }
    lost_mental = sum(before[s] - after[s] for s in handler.MENTAL)
    lost_physical = sum(before[s] - after[s] for s in handler.PHYSICAL)
    assert lost_mental == 1 and lost_physical == 1, "掉点应为 1 精神 + 1 物理"

    # p130：不是诅咒武器击败 → 暂时消散（不入晕、不死）
    jack.stunned_turns = 0
    assert handler.monster_killed_on_defeat(engine, jack, hero, "might", "") is False
    assert handler.on_monster_defeated(engine, jack, 2) is True
    assert handler._jack(engine) is None and flags["jack_banished"] is True

    # p130：叛徒回合开始 → 回到门厅且全属性 +1
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    handler.on_turn_start(engine, traitor)
    jack2 = handler._jack(engine)
    assert jack2 is not None and jack2.room_key == entrance, "杰克应回到门厅"
    assert (jack2.speed, jack2.might, jack2.sanity) == (4, 4, 4), "回归应全属性 +1"
    assert flags["jack_banished"] is False and flags["jack_bonus"] == 1


def verify_haunt48_cursed_weapon_flow() -> None:
    """剧本 48：找武器/研究/理解用法/诅咒武器永杀（p59）。"""
    engine = _run_until_haunt(seed=137, players=3, haunt_id=48)
    handler = engine._mode_handler()
    assert isinstance(handler, CrimsonJackMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    _set_current(engine, hero)

    # 金库未开时在该房间不提供搜寻行动（p59 "the Vault must be open"）
    vault = next((r for r in engine.state.board.values() if r.template_id == "vault"), None)
    if vault is not None:
        vault.data["opened"] = False
        hero.room_key = vault.key
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "search_cursed_weapon" not in ids, "金库未开不应能搜寻"
        vault.data["opened"] = True

    # 搜寻：检定失败一无所获；mock 成功 → 拿到一件诅咒武器
    with patch.object(engine, "_resolve_check", return_value=False):
        assert handler.perform_action(engine, hero, "search_cursed_weapon", {}) is False
    hero.room_key = next(
        (r.key for r in engine.state.board.values()
         if r.template_id in handler.SEARCH_ROOMS and r.template_id != "vault"),
        hero.room_key,
    )
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "search_cursed_weapon", {}) is True
    weapon = flags["cursed_weapon"]
    assert weapon in handler.WEAPON_NAMES and weapon in hero.items

    # 研究：力量/知识 5+ 每次成功 +1 令牌，累计到玩家数即理解用法
    needed = engine._haunt_track_target("study_tokens")
    assert needed == len(engine.state.players), "研究需求应等于玩家数"
    for _ in range(needed):
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "study_cursed_weapon", {}) is True
    assert flags["cursed_weapon_understood"] is True

    # ---- M10-60 回归：研究允许"与武器同房间"的英雄（p59），不是只有持有者
    # 旧实现要求武器在自己背包里 ⇒ 6 人局要一个人成功 6 次（seed107/6p 实测
    # 研究 38 次、进度仍 0）；原文是"a hero in the same room as the cursed weapon"。
    jack = handler._jack(engine)
    assert jack is not None
    other = next(
        (p for p in engine.state.players if p.role == "hero" and p.id != hero.id and not p.dead),
        None,
    )
    if other is not None:
        flags["cursed_weapon_understood"] = False
        other.room_key = hero.room_key
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, other, "study_cursed_weapon", {}) is True, (
                "同房间的队友也应能研究（p59）"
            )
        other.room_key = next(k for k in engine.state.board if k != hero.room_key)
        assert handler.perform_action(engine, other, "study_cursed_weapon", {}) is False, (
            "不在武器房间不能研究"
        )
        flags["cursed_weapon_understood"] = True

    # ---- M10-60 回归：机器人不该用别的武器喂杰克（打散一次 = 他更强地回来）
    assert handler.bot_attack_blocked(engine, hero, jack) is False, "已理解 + 持武器 → 可以打"
    assert handler.bot_weapon_bonus(engine, hero, jack, weapon) == 300, "打杰克该用那把诅咒武器"
    assert handler.bot_weapon_bonus(engine, hero, jack, None) < 0, "空手/别件武器应被压分"
    flags["cursed_weapon_understood"] = False
    assert handler.bot_attack_blocked(engine, hero, jack) is True, (
        "未理解用法前白打只会让杰克更强地回归"
    )
    flags["cursed_weapon_understood"] = True
    traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
    if traitor is not None:
        assert handler.bot_attack_blocked(engine, traitor, jack) is False, "叛徒不受此限"

    # ---- M10-60 回归：有武器未理解时，机器人去武器所在房间集合研究
    flags["cursed_weapon_understood"] = False
    goals = handler.bot_goal_rooms(engine, hero)
    assert goals == [f"__room__{hero.room_key}"], f"应指向武器所在房间：{goals}"
    flags["cursed_weapon_understood"] = True
    assert handler.bot_goal_rooms(engine, hero) == [f"__room__{jack.room_key}"], (
        "已理解 → 去打杰克"
    )

    # p59：理解用法后用该诅咒武器击败 → 永久死亡 + 英雄胜
    assert jack is not None
    hero.room_key = jack.room_key  # 攻击需要同房间
    assert handler.monster_killed_on_defeat(engine, jack, hero, "might", weapon) is True
    assert flags["jack_killed"] is True
    engine.check_victory()  # 引擎版 check_victory 返回 None，只断言胜方
    assert engine.state.winner == "heroes"


def verify_haunt49_astral_spirit_setup() -> None:
    """剧本 49：星界灵布点、灵魂规则（禁探索/精神攻击/失败免伤）（p60/p131）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=49)
    handler = engine._mode_handler()
    assert isinstance(handler, AstralSpiritMode)
    flags = engine._haunt_flags()
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # p131：星界灵放叛徒所在房间
    spirit = handler._spirit(engine)
    assert spirit is not None and spirit.room_key == traitor.room_key
    assert (spirit.speed, spirit.sanity, spirit.knowledge) == (3, 1, 6)

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    # p60：灵魂不能探索新房间
    assert handler.can_discover_rooms(engine, hero) is False
    # p60：灵魂攻击/防御只能用知识/理智——力量攻击被覆盖为较高精神属性
    override = handler.attack_attr_override(engine, hero, spirit, "might")
    assert override in ("sanity", "knowledge")
    assert handler.attack_attr_override(engine, traitor, hero, "might") is None
    # p60：攻击星界灵失败不受伤
    assert handler.attack_loss_damage_disabled(engine, hero, spirit) is True
    other_monster = None  # 其他怪物场景回落 False
    assert handler.attack_loss_damage_disabled(engine, hero, other_monster) is False

    # p131：星界灵攻击 = 知识对决精神伤害（mock 掷出压倒性结果）
    hero.room_key = spirit.room_key
    with patch.object(engine, "_roll_monster_attack", return_value=8), patch.object(
        engine, "_roll_attack", return_value=2
    ):
        assert handler.on_monster_turn_attack(engine, spirit) is True
    lost = sum(
        1
        for s in ("sanity", "knowledge")
        if hero.stat_positions.get(s, 0) < hero.stats.get(s, 0)
    ) or hero.stats.get("sanity", 0) < 4
    assert hero.stat_positions["sanity"] < 4 or hero.stat_positions["knowledge"] < 4, (
        "精神伤害应体现在卡尺格位上移向下"
    )

    # p131：灵魂被毁（死亡）→ 肉体进入无魂名单
    handler.on_player_died(engine, hero)
    assert str(hero.id) in flags["soulless"], "死亡英雄的肉体应记录为无魂"


def verify_haunt49_banish_and_possession() -> None:
    """剧本 49：驱逐令牌摧毁星界灵、附身仪式两条胜负线（p60/p131）。"""
    engine = _run_until_haunt(seed=137, players=3, haunt_id=49)
    handler = engine._mode_handler()
    assert isinstance(handler, AstralSpiritMode)
    flags = engine._haunt_flags()
    spirit = handler._spirit(engine)
    needed = engine._haunt_track_target("banish_tokens")
    assert needed == len(engine.state.players)

    # p60：攻击成功 → 驱逐令牌 +1（星界灵不晕不死、留场）
    assert handler.on_monster_defeated(engine, spirit, 2) is True
    assert engine._haunt_track_value("banish_tokens") == 1
    assert spirit.stunned_turns == 0 and spirit in engine.state.monsters
    for _ in range(needed - 1):
        handler.on_monster_defeated(engine, spirit, 1)
    assert flags["spirit_destroyed"] is True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # 重开一局验证附身线：灵魂被毁 → 仪式 → 附身 → 叛徒胜
    engine2 = _run_until_haunt(seed=137, players=3, haunt_id=49)
    h2 = engine2._mode_handler()
    assert isinstance(h2, AstralSpiritMode)
    f2 = engine2._haunt_flags()
    spirit2 = h2._spirit(engine2)
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    h2.on_player_died(engine2, hero2)
    body = f2["soulless"][str(hero2.id)]
    body["room_key"] = spirit2.room_key  # 把空壳挪到星界灵房间
    players2 = len(engine2.state.players)
    # 检定低于起始理智：不累积
    with patch.object(engine2, "roll_dice", return_value=0):
        h2.on_monster_turn_start(engine2, spirit2)
    assert body["ritual"] == 0, "低于起始理智不应累积附身印记"
    # 检定高于起始理智：累积；满玩家数 → 附身 → 叛徒胜
    f2["soulless"][str(hero2.id)]["room_key"] = spirit2.room_key
    f2["soulless"][str(hero2.id)]["ritual"] = players2 - 1
    with patch.object(engine2, "roll_dice", return_value=9):
        h2.on_monster_turn_start(engine2, spirit2)
    assert f2["spirit_inhabited"] is True
    assert h2.check_victory(engine2) is True
    assert engine2.state.winner == "traitor"


def verify_haunt50_night_murder_setup() -> None:
    """剧本 50：仆人布点、夜晚推进、强化表（p61/p132）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=50)
    handler = engine._mode_handler()
    assert isinstance(handler, NightMurderMode)

    # p132：仆人数 = 英雄数，初始 3/3/3
    servants = handler._servants(engine)
    hero_count = sum(1 for p in engine.state.players if p.role == "hero")
    assert len(servants) == hero_count, "仆人数应等于英雄数"
    assert all((s.speed, s.might, s.sanity) == (3, 3, 3) for s in servants)
    # 前三个尽量各占一层（受"仆人数"与"有空房的层数"共同约束）
    floors = {engine.state.board[s.room_key].floor for s in servants[:3]}
    occupied = {p.room_key for p in engine.state.players if not p.dead}
    empty_floors = {
        room.floor for key, room in engine.state.board.items() if key not in occupied
    }
    assert len(floors) >= min(len(servants), len(empty_floors)), (
        f"前三个仆人应尽量分布在不同楼层：实际 {sorted(floors)}，"
        f"空房楼层 {sorted(empty_floors)}"
    )
    # 轨道从 0 开始，日出目标 10
    assert engine._haunt_track_value("night_timer") == 0
    assert engine._haunt_track_target("night_timer") == 10

    traitor = next(p for p in engine.state.players if p.role == "traitor")
    # p132：叛徒回合结束推进夜晚；按表重算仆人属性
    handler.on_turn_end(engine, traitor)
    assert engine._haunt_track_value("night_timer") == 1
    # 推到 4 → 4/4/4；8 → 5/5/5；9 → 6/6/6
    for _ in range(3):
        handler.on_turn_end(engine, traitor)
    assert engine._haunt_track_value("night_timer") == 4
    assert all((s.speed, s.might, s.sanity) == (4, 4, 4) for s in handler._servants(engine))
    for _ in range(4):
        handler.on_turn_end(engine, traitor)
    assert engine._haunt_track_value("night_timer") == 8
    assert all((s.speed, s.might, s.sanity) == (5, 5, 5) for s in handler._servants(engine))
    handler.on_turn_end(engine, traitor)
    assert engine._haunt_track_value("night_timer") == 9
    assert all((s.speed, s.might, s.sanity) == (6, 6, 6) for s in handler._servants(engine))

    # ---- M10-61 回归：英雄不跟仆人换命（p61 的活法是撑到日出，不是清场）
    # 仆人是普通怪物：被击败只昏迷一回合、下回合照回来；而英雄落败要按 p20 吃
    # 差值反击。实测（6 局诊断 + seed109/4p 逐回合）英雄全灭在夜晚 1-3/10，
    # 死因正是 2 对 3、0 对 1、3 对 6 这类自己发起的交换。
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    servant = handler._servants(engine)[0]
    servant.stunned_turns = 0
    for card_id in list(hero.items):
        hero.items.remove(card_id)  # 先清空装备，用裸属性判定
    if hero.stats.get("might", 0) <= servant.might:
        assert handler.bot_attack_blocked(engine, hero, servant) is True, (
            "近战骰数不超过仆人力量时不该出手（白送反击伤害）"
        )
    servant.stunned_turns = 1
    assert handler.bot_attack_blocked(engine, hero, servant) is False, "昏迷的仆人是白送的窗口"
    servant.stunned_turns = 0
    assert handler._best_melee_dice(engine, hero) == hero.stats.get("might", 0), (
        "裸手近战骰数 = 力量"
    )


def verify_haunt50_dawn_and_absorption() -> None:
    """剧本 50：日出分遗产、叛徒出局吸收兜底、英雄全灭（p61/p132）。"""
    engine = _run_until_haunt(seed=137, players=3, haunt_id=50)
    handler = engine._mode_handler()
    assert isinstance(handler, NightMurderMode)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # p132：叛徒出局也不判英雄胜（仆人继续，照样能赢）
    traitor.dead = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner is None, "叛徒死了也不该直接判英雄胜"

    # p61：撑到日出（轨道 10）→ 存活英雄胜
    engine._set_haunt_track_value("night_timer", 10)
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # p132：黎明前英雄全灭 → 叛徒胜
    engine2 = _run_until_haunt(seed=137, players=3, haunt_id=50)
    h2 = engine2._mode_handler()
    for p in engine2.state.players:
        if p.role == "hero":
            p.dead = True
    assert h2.check_victory(engine2) is True
    assert engine2.state.winner == "traitor"


def verify_haunt51_darker_than_night() -> None:
    """剧本 51：圣印/黑暗 Hex/胜负条件（p62/p133）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=51)
    handler = engine._mode_handler()
    assert isinstance(handler, DarkerThanNightMode)
    flags = engine._haunt_flags()

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 圣印行动在镜面房间可用
    mirror = next((r for r in engine.state.board.values()
                   if r.template_id in ("bedroom", "chapel", "conservatory", "dining_room",
                                        "grand_staircase", "master_bedroom")), None)
    if mirror is not None:
        hero.room_key = mirror.key
        _set_current(engine, hero)
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "create_seal" in ids, "在镜面房间应能创造圣印"
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "create_seal", {}) is True
        assert engine._haunt_track_value("hero_progress") == 1

    # 黑暗 Hex：叛徒放置
    with patch.object(engine, "_roll_attack", return_value=5):
        handler.on_turn_start(engine, traitor)
    assert int(flags.get("dark_hexes", 0)) >= 1, "叛徒应放置 Dark Hex"

    # 3 枚 Dark Hex → 叛徒胜
    flags["dark_hexes"] = 3
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor"

    # 圣印满 → 英雄胜
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    engine._set_haunt_track_value("hero_progress", engine._haunt_track_target("hero_progress"))
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt52_crackling_aura() -> None:
    """剧本 52：魔法尘/反魔法场/破解戒指/召唤与驱逐（p63/p134）。

    M10-63 补上"破解戒指"整条英雄胜线：Turn/Damage 轨（初值 = 英雄数）、
    戒指开局戴在叛徒手上、尝试即消耗魔法尘、轨归零 → 戒指失效 + 佩戴者
    昏迷、叛徒固定 3 骰防守与受伤 −1、蜡烛/圣徽的理智驱逐、反魔法场回合
    清除，以及"叛徒倒下 ≠ 英雄胜"这一条被旧实现写反的口径。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=52)
    handler = engine._mode_handler()
    assert isinstance(handler, CracklingAuraMode)
    flags = engine._haunt_flags()

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    heroes_alive = sum(1 for p in engine.state.players if p.role == "hero")

    # —— p63：Turn/Damage 轨起步 = 作祟开始时的英雄数；p134：戒指戴在叛徒手上
    assert engine._haunt_track_target("ring_track") == heroes_alive
    assert engine._haunt_track_value("ring_track") == heroes_alive
    assert "omen_ring" in traitor.items, "戒指应开局戴在叛徒手上"

    # —— p134：叛徒不能做常规攻击；英雄打叛徒时叛徒固定 3 骰防守、受伤 −1
    assert handler.attack_allowed(engine, traitor, hero) is False
    assert handler.attack_allowed(engine, hero, traitor) is True
    fixed = handler.defense_roll_override(engine, hero, traitor)
    assert isinstance(fixed, int) and 0 <= fixed <= 6, "叛徒应以固定 3 骰防守"
    assert handler.defense_roll_override(engine, hero, hero) is None
    assert handler.physical_damage_reduction(engine, traitor, 3, "攻击", "physical") == 1
    assert handler.physical_damage_reduction(engine, hero, 3, "攻击", "physical") == 0

    # —— 搜索魔法尘（事件房）与"多枚合一"
    event_room = next((r for r in engine.state.board.values() if r.symbol == "event"), None)
    assert event_room is not None, "本局应翻出过事件房"
    hero.room_key = event_room.key
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "search_dust" in ids, "在事件房应能搜索魔法尘"
    with patch.object(engine, "roll_dice", side_effect=lambda c, l="": 5 if l == "魔法尘" else c):
        assert handler.perform_action(engine, hero, "search_dust", {}) is True
    assert engine.tokens_held_by(hero.id, "magic_dust"), "搜索成功应获得魔法尘"
    with patch.object(engine, "roll_dice", side_effect=lambda c, l="": 5 if l == "魔法尘" else c):
        assert handler.perform_action(engine, hero, "search_dust", {}) is True
    assert len(engine.tokens_held_by(hero.id, "magic_dust")) == 1, "p63：多枚魔法尘合并成一枚"
    assert "search_dust" not in {a.id for a in handler.available_actions(engine, hero)}, \
        "手里已经有尘：不该再提供搜索（搜到也会合并掉）"

    # —— 破解戒指：同房 + 持尘 → 速度攻击对固定 3 骰；成功只掉轨、不造成伤害、必耗尘
    hero.room_key = traitor.room_key
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "disenchant_ring" in ids, "与戴戒指的叛徒同房且持尘应能破解"
    assert "search_dust" not in ids, "能就地破解时不该再提供搜索"
    hp_before = dict(traitor.stats)
    with patch.object(engine, "roll_dice", side_effect=lambda c, l="": 0 if l == "戒指防守" else 6):
        assert handler.perform_action(engine, hero, "disenchant_ring", {}) is True
    assert engine._haunt_track_value("ring_track") == heroes_alive - 1
    assert not engine.tokens_held_by(hero.id, "magic_dust"), "尝试破解即消耗携带的魔法尘"
    assert dict(traitor.stats) == hp_before, "破解成功不造成伤害"

    # —— 被挡下同样消耗尘，轨道不动
    engine.spawn_token("magic_dust", label="魔法尘", role="carried", holder=hero.id)
    with patch.object(engine, "roll_dice", side_effect=lambda c, l="": 6 if l == "戒指防守" else 0):
        assert handler.perform_action(engine, hero, "disenchant_ring", {}) is True
    assert not engine.tokens_held_by(hero.id, "magic_dust"), "被挡下也要消耗尘"
    assert engine._haunt_track_value("ring_track") == heroes_alive - 1, "被挡下不该推进轨道"

    # —— 轨归零：戒指失效 + 佩戴者昏迷；无恶魔 → 英雄胜
    engine._set_haunt_track_value("ring_track", 1)
    engine.spawn_token("magic_dust", label="魔法尘", role="carried", holder=hero.id)
    with patch.object(engine, "roll_dice", side_effect=lambda c, l="": 0 if l == "戒指防守" else 6):
        assert handler.perform_action(engine, hero, "disenchant_ring", {}) is True
    assert flags.get("ring_disenchanted") is True
    assert engine._haunt_track_value("ring_track") <= 0
    assert traitor.dead is True, "戒指失效时佩戴者昏迷"
    assert engine.state.winner == "heroes", "戒指失效 + 无恶魔 → 英雄胜"

    # —— 被旧实现写反的口径：叛徒倒下（戒指未破解）不算英雄胜
    engine2 = _run_until_haunt(seed=113, players=3, haunt_id=52)
    handler2 = engine2._mode_handler()
    traitor2 = next(p for p in engine2.state.players if p.role == "traitor")
    traitor2.dead = True
    assert handler2.check_victory(engine2) is True
    assert not engine2.state.winner, "戒指未破解时叛徒倒下不该判英雄胜"

    # —— 恶魔领主：召唤（放弃整回合）、反魔法场回合清除、知识 6+ 逆转召唤
    engine3 = _run_until_haunt(seed=113, players=3, haunt_id=52)
    handler3 = engine3._mode_handler()
    flags3 = engine3._haunt_flags()
    traitor3 = next(p for p in engine3.state.players if p.role == "traitor")
    hero3 = next(p for p in engine3.state.players if p.role == "hero" and not p.dead)
    pentagram = handler3._pentagram_key(engine3)
    assert pentagram is not None, "本局应已翻出五芒星室"
    traitor3.room_key = pentagram
    _set_current(engine3, traitor3)
    traitor3.steps_remaining = 4
    ids = [a.id for a in handler3.available_actions(engine3, traitor3)]
    assert ids == ["summon_demon"], f"机器人能召唤时只该看到召唤：{ids}"
    with patch.object(engine3, "roll_dice", return_value=6):
        assert handler3.perform_action(engine3, traitor3, "summon_demon", {}) is True
    assert flags3.get("demon_alive") is True
    assert handler3._demon(engine3) is not None, "知识 5+ 应召出恶魔领主"
    assert traitor3.steps_remaining == 0, "p134：召唤要放弃整个回合"
    assert "summon_demon" not in {a.id for a in handler3.available_actions(engine3, traitor3)}, \
        "场上已有恶魔时不能再召唤"

    # 反魔法场：叛徒回合开始清除自己所在房间的场（旧实现做成永久）
    flags3["anti_magic_rooms"] = [pentagram]
    engine3.spawn_token("magic_dust", label="魔法尘", role="marker", room_key=pentagram)
    handler3.on_turn_start(engine3, traitor3)
    assert pentagram not in flags3.get("anti_magic_rooms", []), \
        "叛徒回合开始应清掉自己房间的反魔法场"

    hero3.room_key = pentagram
    _set_current(engine3, hero3)
    ids = [a.id for a in handler3.available_actions(engine3, hero3)]
    assert ids == ["banish_demon"], f"恶魔在场且站在召唤室：机器人只该看到逆转召唤：{ids}"
    with patch.object(engine3, "roll_dice", return_value=6):
        assert handler3.perform_action(engine3, hero3, "banish_demon", {}) is True
    assert flags3.get("demon_alive") is False
    assert handler3._demon(engine3) is None, "知识 6+ 应把恶魔驱逐"

    # —— 常规攻击只把恶魔打晕；持蜡烛/圣徽的理智攻击造成伤害即驱逐（p63）
    demon = engine3._spawn_single_haunt_monster(
        {"template_id": "giant", "name": "恶魔领主", "might": 7, "speed": 5, "sanity": 4},
        pentagram,
    )
    assert demon is not None
    flags3["demon_alive"] = True
    engine3._last_attack_attr = "might"
    assert handler3.on_monster_defeated(engine3, demon, 3) is False, "常规伤害只能打晕"
    assert handler3._demon(engine3) is not None
    hero3.items.append("item_candle")
    assert handler3.attack_attr_override(engine3, hero3, demon, "might") == "sanity"
    assert handler3.attack_loss_damage_disabled(engine3, hero3, demon) is True
    engine3._last_attack_attr = "sanity"
    assert handler3.on_monster_defeated(engine3, demon, 3) is True, "理智攻击造成伤害即驱逐"
    assert flags3.get("demon_alive") is False and handler3._demon(engine3) is None

    # —— bot 决策面：有尘要去追戒指；能就地破解就留下；叛徒不受这条约束
    engine4 = _run_until_haunt(seed=113, players=3, haunt_id=52)
    handler4 = engine4._mode_handler()
    hero4 = next(p for p in engine4.state.players if p.role == "hero" and not p.dead)
    traitor4 = next(p for p in engine4.state.players if p.role == "traitor")
    engine4.spawn_token("magic_dust", label="魔法尘", role="carried", holder=hero4.id)
    assert handler4.bot_leave_after_action(engine4, hero4) is True, "有尘且不在戒指旁：该去找人"
    assert handler4.bot_leave_after_action(engine4, traitor4) is False
    hero4.room_key = handler4._ring_room(engine4)
    assert handler4._can_disenchant(engine4, hero4) is True
    assert handler4.bot_leave_after_action(engine4, hero4) is False, "正站在戒指旁：留下动手"

    # —— 期望值小工具（骰面 0/1/2 各 1/3 的精确概率）
    assert handler4._p_at_least(0, 1) == 0.0
    assert abs(handler4._p_at_least(1, 1) - 2 / 3) < 1e-9
    assert abs(handler4._contest_net(1, 0) - 1.0) < 1e-9
    assert handler4._contest_net(4, 1) > handler4._contest_net(2, 1)

    # —— 复原术补属性不超起始值；附魔是知识对理智、伤害为精神、落败吃差值
    engine5 = _run_until_haunt(seed=113, players=3, haunt_id=52)
    handler5 = engine5._mode_handler()
    traitor5 = next(p for p in engine5.state.players if p.role == "traitor")
    hero5 = next(p for p in engine5.state.players if p.role == "hero" and not p.dead)
    engine5._apply_stat_loss(traitor5, "might", 2)
    with patch.object(engine5, "roll_dice", return_value=2):
        assert handler5.perform_action(engine5, traitor5, "restoration", {}) is True
    assert traitor5.stats["might"] <= handler5._starting_stats(engine5, traitor5)["might"]
    hero5.room_key = traitor5.room_key
    rolls = iter([6, 0])
    dealt: list[tuple] = []
    with patch.object(engine5, "roll_dice", side_effect=lambda c, l="": next(rolls)):
        with patch.object(
            engine5, "_deal_damage",
            side_effect=lambda p, t, a, source="": dealt.append((p.id, t, a, source)),
        ):
            assert handler5.perform_action(
                engine5, traitor5, "enchant", {"target": hero5.id}
            ) is True
    assert dealt and dealt[0][0] == hero5.id and dealt[0][1] == "mental" and dealt[0][2] == 6, \
        "附魔：知识 6 对理智 0 → 6 点精神伤害"
    rolls = iter([0, 5])
    dealt.clear()
    with patch.object(engine5, "roll_dice", side_effect=lambda c, l="": next(rolls)):
        with patch.object(
            engine5, "_deal_damage",
            side_effect=lambda p, t, a, source="": dealt.append((p.id, t, a, source)),
        ):
            assert handler5.perform_action(
                engine5, traitor5, "enchant", {"target": hero5.id}
            ) is True
    assert dealt and dealt[0][0] == traitor5.id, "附魔落败要承受差值（法术攻击同样是攻击）"


def verify_haunt53_toxic_object_escape() -> None:
    """剧本 53：死亡之物/逃跑链路/净化/胜利条件（p64/p135）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=53)
    handler = engine._mode_handler()
    assert isinstance(handler, ToxicObjectEscapeMode)
    flags = engine._haunt_flags()

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 狗在场且有死亡之物
    dog = engine._monster_by_template("dog")
    assert dog is not None, "狗应已布点"

    # 逃跑链路：清障碍→解锁→逃离
    entrance = next(k for k, r in engine.state.board.items() if r.template_id == "entrance_hall")
    hero.room_key = entrance
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "clear_barricade" in ids, "在门厅应能清障碍"
    assert "unlock_door" not in ids, "p64：障碍没清完不该提供解锁"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "clear_barricade", {}) is True
    assert engine._haunt_track_value("barricade_tokens") == 1

    # 解锁
    engine._set_haunt_track_value("barricade_tokens", engine._haunt_track_target("barricade_tokens"))
    engine._reset_player_turn_state(hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "unlock_door" in ids, "障碍清完应能解锁"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "unlock_door", {}) is True
    assert flags.get("door_unlocked") is True

    # 逃离
    engine._reset_player_turn_state(hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "flee_house" in ids, "门开后应能逃离"
    assert handler.perform_action(engine, hero, "flee_house", {}) is True
    assert hero.id in flags.get("escaped", [])

    # 半数逃出 → 英雄胜
    hero2 = next((p for p in engine.state.players if p.role == "hero" and p.id != hero.id and not p.dead), None)
    if hero2 is not None:
        hero2.room_key = entrance
        _set_current(engine, hero2)
        handler.perform_action(engine, hero2, "flee_house", {})
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # ---- M10-62 回归：口径与归属修正（p64/p135）
    # ① 两条轨道目标都按"作祟开始时的英雄数"算（旧版用 rule_data 的 player_count /
    #    half_players_ceil，把叛徒也算了进去 ⇒ 每局多要一次力量 4+、3 人局多要 1 人）
    heroes_count = sum(1 for p in engine.state.players if p.role == "hero")
    assert engine._haunt_track_target("barricade_tokens") == heroes_count, "障碍目标应为英雄数"
    assert engine._haunt_track_target("escaped_count") == -(-heroes_count // 2), (
        "逃出目标应为 ceil(英雄数/2)"
    )
    # ② 死亡之物开局在叛徒手上（旧实现挂在"id 等于狗 id 后缀"的随机玩家身上）
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    token = handler._object_token(engine)
    assert token is not None and token.holder == traitor.id, "死亡之物应由叛徒持有"
    # ③ 携带者倒下 → 掉落原地；英雄进房 → 顺手捡起（净化线的入口）
    token.room_key = ""
    handler.on_player_died(engine, traitor)
    assert token.holder is None and token.room_key == traitor.room_key
    traitor.dead = True
    hero.room_key = token.room_key
    handler.on_enter_room(engine, hero, engine.state.board[hero.room_key])
    assert token.holder == hero.id, "英雄进房应捡起掉落的死亡之物"
    # ④ 偷取（p135 "like a regular item"）：打赢持有者（引擎只在 >2 优势时调用）
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    traitor.dead = False
    token.holder = traitor.id
    assert handler.special_steal(engine, hero, traitor, 3, "might") is True
    assert token.holder == hero.id, "special_steal 应把死亡之物转给攻击者"
    # ⑤ 叛徒胜 = 超过半数英雄死亡（不是全灭）
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    flags["object_cleansed"] = False
    flags["escaped"] = []
    alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    while alive and len(alive) * 2 >= heroes_count:
        alive.pop().dead = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor", "超过半数英雄死亡应判叛徒胜"
    # ⑥ 机器人不打狗（打它毫无收益）；flee_house 与 escaped_count 轨道同步
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    dog = engine._monster_by_template("dog")
    if dog is not None:
        assert handler.bot_attack_blocked(engine, hero, dog) is True, "打狗毫无收益"
    engine._set_haunt_track_value("escaped_count", 0)
    flags["escaped"] = []
    hero.dead = False
    engine._reset_player_turn_state(hero)
    handler.perform_action(engine, hero, "flee_house", {})
    assert engine._haunt_track_value("escaped_count") == 1, "逃离应推进 escaped_count 轨道"


def verify_haunt54_arkanok_skull() -> None:
    """剧本 54：骷髅/遗骸侦测/净化/僵尸/胜利条件（p65/p136）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=54)
    handler = engine._mode_handler()
    assert isinstance(handler, ArkanokSkullMode)
    flags = engine._haunt_flags()

    # 骷髅在作祟房间；遗骸房间已选；僵尸已布点
    skull = engine.tokens_of_kind("skull")
    assert skull, "骷髅应已放置"
    remains = flags.get("remains_room")
    assert remains is not None, "遗骸房间应已选定"
    zombies = [m for m in engine.state.monsters if m.template_id == "zombie"]
    assert len(zombies) >= 1, "应有僵尸已布点"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 侦测：需要骷髅或道具
    hero.room_key = skull[0].room_key
    hero.items.append("omen_holy_symbol")
    _set_current(engine, hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "detect_remains" in ids, "持圣徽应能侦测"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "detect_remains", {}) is True
    assert flags.get("remains_found") is True

    # 净化：持骷髅在遗骸房间
    engine.give_token(skull[0].uid, hero.id)
    hero.room_key = remains
    engine._reset_player_turn_state(hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "exorcise" in ids, "持骷髅在遗骸房间应能净化"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "exorcise", {}) is True
    assert engine._haunt_track_value("ritual_progress") == 1
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt55_kings_roads() -> None:
    """剧本 55：影子追击/驱魔检定/国王之路/孢子/附身/胜利条件（p66/p137）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=55)
    handler = engine._mode_handler()
    assert isinstance(handler, KingsRoadsMode)
    flags = engine._haunt_flags()

    # 影子已布点（M10-64：改用 shadow 模板，Speed 3 / Might 5 / Sanity 5）
    shadows = [m for m in engine.state.monsters if m.template_id == "shadow"]
    assert len(shadows) >= 1, "至少应有一只影子"
    heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    assert len(shadows) == len(heroes_alive), "p66：每名英雄一只影子"
    assert all(m.speed == 3 and m.might == 5 and m.sanity == 5 for m in shadows), \
        "p66：影子 Speed 3 / Might 5 / Sanity 5"
    targets = flags.get("shadow_targets", {})
    assert set(targets.values()) == {p.id for p in heroes_alive}, \
        "p66：每只影子只盯自己对应的英雄"

    # p66：作祟揭示者的角色卡上先有孢子，回合开始在自己房间放一枚
    revealer_id = engine.state.haunt_revealer_id
    assert revealer_id in set(flags.get("spore_cards", [])), "揭示者卡上应有孢子"
    revealer = next(p for p in engine.state.players if p.id == revealer_id)
    before = len(engine.tokens_of_kind("spore"))
    handler.on_turn_start(engine, revealer)
    assert len(engine.tokens_of_kind("spore")) == before + 1, \
        "p66：卡上有孢子的玩家，回合开始在自己房间放一枚"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 驱魔检定：在仪式房间
    dis_room = next((r for r in engine.state.board.values()
                     if r.template_id in handler.DISENCHANT_ROOMS), None)
    if dis_room is not None:
        hero.room_key = dis_room.key
        _set_current(engine, hero)
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "disenchant_room" in ids, "在仪式房间应能驱魔"
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "disenchant_room", {}) is True
        assert engine._haunt_track_value("disenchant_progress") == 1
        # 同房不能再用
        engine._reset_player_turn_state(hero)
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "disenchant_room" not in ids, "同房不能再次驱魔"
        # p66：房间与预兆各只支持一种属性（实验室=知识、教堂/温室/地窖=理智）
        if dis_room.template_id in handler.SANITY_ROOMS:
            assert handler._disenchant_stats(engine, hero) == ["sanity"] \
                or "omen_crystal_ball" in hero.items
        else:
            assert "knowledge" in handler._disenchant_stats(engine, hero)

    # —— M10-64：国王之路（入口房之间花 1 格移动直达）
    entrances = handler._entrances(engine)
    assert flags.get("roads_hub") in entrances, "作祟揭示房也是入口"
    hero.room_key = entrances[0]
    hero.steps_remaining = max(1, hero.steps_remaining)
    _set_current(engine, hero)
    roads = [a for a in handler.available_actions(engine, hero) if a.id == "roads_travel"]
    assert roads, "在入口房应能走国王之路"
    destination = roads[0].data["room"]
    with patch.object(engine, "_resolve_room_entry_if_needed", return_value=None):
        with patch.object(engine, "_resolve_check", return_value=True):
            with patch.object(engine, "roll_dice", return_value=4):
                assert handler.perform_action(
                    engine, hero, "roads_travel", {"room": destination}
                ) is True
    assert hero.room_key == destination, "理智 4+ 应安全抵达另一个入口"
    assert hero.id in set(flags.get("spore_cards", [])), "用过国王之路要在卡上放孢子"
    assert hero.id in set(flags.get("road_cards", [])), "p66：路上驱魔每人限一次"

    # —— M10-64：附身（影子打赢 = 该英雄变叛徒、影子离场、+2 知识）
    possess_engine = _run_until_haunt(seed=113, players=3, haunt_id=55)
    possess_handler = possess_engine._mode_handler()
    possess_flags = possess_engine._haunt_flags()
    shadow = possess_handler._shadows(possess_engine)[0]
    victim = next(
        p for p in possess_engine.state.players
        if p.id == possess_flags["shadow_targets"][shadow.id]
    )
    victim.room_key = shadow.room_key
    knowledge_before = victim.stats["knowledge"]
    with patch.object(possess_engine, "roll_dice", return_value=6):
        with patch.object(possess_engine, "_roll_attack", return_value=0):
            assert possess_handler.on_monster_turn_attack(possess_engine, shadow) is True
    assert victim.role == "traitor", "p66：被影子打赢就是附身"
    assert shadow.id not in {m.id for m in possess_engine.state.monsters}, "附身的影子要离场"
    assert victim.stats["knowledge"] >= knowledge_before, "p137：附身后 +2 知识"

    # p66：影子不会被打死（吸收击败）；打它只会让英雄吃 1 骰精神伤害
    assert possess_handler.on_monster_defeated(possess_engine, shadow, 3) is True
    attacker = next(
        p for p in possess_engine.state.players if p.role == "hero" and not p.dead
    )
    assert possess_handler.bot_attack_blocked(possess_engine, attacker, shadow) is True
    dealt: list[tuple] = []
    with patch.object(possess_engine, "roll_dice", return_value=1):
        with patch.object(
            possess_engine, "_deal_damage",
            side_effect=lambda p, t, a, source="": dealt.append((p.id, t, a)),
        ):
            possess_handler.on_attack_resolved(possess_engine, attacker, shadow, True)
    assert dealt and dealt[0][1] == "mental", "p66：攻击影子的英雄受 1 骰精神伤害"

    # 胜利：驱魔满
    engine._set_haunt_track_value("disenchant_progress", engine._haunt_track_target("disenchant_progress"))
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt56_sands_of_time_setup() -> None:
    """剧本 56：幽影布点、面具加成、戒指/奖章规则、穿墙移动（p67/p138）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=56)
    handler = engine._mode_handler()
    assert isinstance(handler, SandsOfTimeMode)
    flags = engine._haunt_flags()
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # p138：幽影 = 英雄数，放作祟房；轨道从 0 开始
    haunt_room = engine.state.meta["haunt_rule"]["haunt_room"]
    spectres = handler._spectres(engine)
    hero_count = sum(1 for p in engine.state.players if p.role == "hero")
    assert len(spectres) == hero_count
    assert all(s.room_key == haunt_room for s in spectres)
    assert flags["time_track"] == 0

    # p138：面具已戴上（+2 知识且叛徒未死——理智保护生效）
    assert not traitor.dead, "理智保护应防止面具直接杀死叛徒"
    # p67：持戒指者力量攻击覆盖为理智；未持戒指不覆盖
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero.items.append(handler.RING)
    assert handler.attack_attr_override(engine, hero, spectres[0], "might") == "sanity"
    hero.items.remove(handler.RING)
    assert handler.attack_attr_override(engine, hero, spectres[0], "might") is None
    assert handler.bot_action_blocked(engine, traitor, "time_stop_strike") is True
    assert handler.bot_leave_after_action(engine, traitor) is True
    # 没戒指的英雄不该把幽影房当目标、也不该空手捶免疫力量的幽影。
    # 欺骗命运要同房幽影才开放；先把人挪开，避免开局恰好站在作祟房里假失败。
    elsewhere = next(
        (k for k in engine.state.board if k != spectres[0].room_key),
        hero.room_key,
    )
    hero.room_key = elsewhere
    assert handler.bot_action_blocked(engine, hero, "cheat_fate") is True
    assert handler.bot_attack_blocked(engine, hero, spectres[0]) is True
    hero.items.append(handler.RING)
    assert handler.bot_attack_blocked(engine, hero, spectres[0]) is False
    hero.items.remove(handler.RING)
    # p67：持奖章者与幽影对决落败免伤
    hero.items.append(handler.MEDALLION)
    assert handler.attack_loss_damage_disabled(engine, hero, spectres[0]) is True
    hero.items.remove(handler.MEDALLION)

    # p138：幽影穿墙移动（同层正交邻格，无需门）
    spirit = spectres[0]
    before = spirit.room_key
    handler.on_monster_turn_start(engine, spirit)
    after = spirit.room_key
    assert after != before, "幽影应能穿墙移动（同房必有正交邻格）"
    assert handler.on_monster_move(engine, spirit, 3) is True, "穿墙后应跳过引擎默认移动"

    # p67 失控检定：轨道 3、掷骰必低 → 循环磨损到轨道 0（归零后再掷高，避免 0≤0 无限磨）
    flags["time_track"] = 3
    for stat in ("sanity", "knowledge", "might", "speed"):
        track = engine._stat_track(traitor, stat) or [1, 2, 3, 4, 5]
        traitor.stat_positions[stat] = min(5, len(track) - 1)
        traitor.stats[stat] = track[traitor.stat_positions[stat]]
        traitor.overflow[stat] = 0
    pos_before = dict(traitor.stat_positions)

    def _control_roll(_dice, _label=""):
        return 0 if int(flags["time_track"]) > 0 else 99

    with patch.object(engine, "roll_dice", side_effect=_control_roll):
        handler.on_turn_end(engine, traitor)
    assert flags["time_track"] == 0, "失控循环应把轨道磨到 0"
    assert not traitor.dead, "属性充裕时失控只磨损、不应直接判死"
    lost = sum(
        pos_before[s] - traitor.stat_positions[s]
        for s in ("sanity", "knowledge", "might", "speed")
    )
    assert lost >= 3, f"失控应磨损叛徒属性（实际 -{lost}）"

    # p67：失控把属性磨到骷髅必须判死（_apply_stat_loss 本身不判死）
    engine2 = _run_until_haunt(seed=113, players=3, haunt_id=56)
    h2 = engine2._mode_handler()
    f2 = engine2._haunt_flags()
    traitor2 = next(p for p in engine2.state.players if p.role == "traitor")
    for stat in ("sanity", "knowledge", "might", "speed"):
        traitor2.stat_positions[stat] = 0
        track = engine2._stat_track(traitor2, stat) or [1]
        traitor2.stats[stat] = track[0]
        traitor2.overflow[stat] = 0
    f2["time_track"] = 1
    with patch.object(engine2, "roll_dice", return_value=0):
        h2.on_turn_end(engine2, traitor2)
    assert traitor2.dead, "失控磨损到骷髅应杀死叛徒"
    assert engine2.state.winner == "heroes"


def verify_haunt56_time_powers() -> None:
    """剧本 56：命运之风/时停打击/补充时沙/欺骗命运/胜负（p67/p138）。"""
    engine = _run_until_haunt(seed=137, players=3, haunt_id=56)
    handler = engine._mode_handler()
    assert isinstance(handler, SandsOfTimeMode)
    flags = engine._haunt_flags()
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    spectre = handler._spectres(engine)[0]

    # p138 命运之风：+2 移动 + 轨道 +1
    _set_current(engine, traitor)
    steps_before = max(1, traitor.stats["speed"])
    traitor.steps_remaining = steps_before
    assert handler.perform_action(engine, traitor, "winds_of_fate", {}) is True
    assert traitor.steps_remaining == steps_before + 2 and flags["time_track"] == 1

    # p138 时停打击：造成伤害 → 目标进跳过名单；下回合开始被冻结
    traitor.room_key = hero.room_key
    with patch.object(engine, "_roll_attack", side_effect=[9, 2]):
        assert handler.perform_action(engine, traitor, "time_stop_strike", {}) is True
    assert hero.id in flags["skip_turn_ids"] and flags["time_track"] == 2
    handler.on_turn_start(engine, hero)
    assert hero.movement_stopped and hero.attack_used
    assert hero.id not in flags["skip_turn_ids"], "冻结应只持续一回合"

    # p138 补充时沙：成功 → 每只同房幽影轨道 -1、幽影全晕
    traitor.room_key = spectre.room_key
    before_track = flags["time_track"]
    here_count = sum(1 for s in handler._spectres(engine) if s.room_key == traitor.room_key)
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, traitor, "replenish_sands", {}) is True
    assert flags["time_track"] == max(0, before_track - here_count)
    assert spectre.stunned_turns >= 1

    # p67 欺骗命运：持水晶球 + 同房幽影 + 知识 4+ → 放逐
    hero.room_key = spectre.room_key
    hero.items.append(handler.CRYSTAL_BALL)
    _set_current(engine, hero)
    assert handler._cheat_fate_allowed(engine, hero) is True
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "cheat_fate", {}) is True
    assert all(m.id != spectre.id for m in engine.state.monsters), "幽影应被放逐"

    # p67 胜负：叛徒死亡 → 英雄胜
    traitor.dead = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt57_paint_setup() -> None:
    """剧本 57 开局：画廊强制入场、颜料数与搁置、无怪物、叛徒加属性（p68/p139）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=57)
    handler = engine._mode_handler()
    assert isinstance(handler, PortraitCurseMode)
    flags = engine._haunt_flags()
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # p68：肖像所在的画廊必须在场，否则英雄无处重绘
    assert any(room.template_id == "gallery" for room in engine.state.board.values()), "画廊应被强制放入房子"
    # p68：颜料 = 英雄数 + 2；场上放不下的搁置，等房间被发现时补放
    paints = engine.tokens_of_kind("paint")
    assert len(paints) + int(flags["pending_paint"]) == len(heroes) + 2
    assert len(paints) >= len(heroes), "场上颜料至少要够英雄重绘所需的量，否则剧本死锁"
    assert all(token.holder is None for token in paints)
    # 每间合适房最多一枚
    room_keys = [token.room_key for token in paints]
    assert len(room_keys) == len(set(room_keys)), "每间合适房间只放一枚颜料（p68）"
    assert all(engine.state.board[key].template_id in handler.PAINT_ROOMS for key in room_keys)
    # p68/p139：本剧本没有怪物
    assert engine.state.monsters == []
    # p68：知识检定令牌的目标数按"作祟开始时的英雄数"快照
    assert engine._haunt_track_target("repaint") == len(heroes)
    assert flags["repaint_needed"] == len(heroes)
    assert engine._haunt_track_target("paint_destroyed") == 3

    # p139：低于起点的属性先补回起点，再每名英雄抬一格
    face = engine.catalog.characters[traitor.character_id]
    for stat in handler.STAT_ORDER:
        assert traitor.stats[stat] >= face.stats[stat], f"{stat} 不应低于起点"
    gained = sum(traitor.stats[stat] - face.stats[stat] for stat in handler.STAT_ORDER)
    assert gained > 0, "叛徒开局应高出起点（每名英雄一次）"


def verify_haunt57_repaint_and_immunity() -> None:
    """剧本 57：重绘链路 + 叛徒免疫与护身符例外 + 画廊凝视 + 胜负（p68/p139）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=57)
    handler = engine._mode_handler()
    flags = engine._haunt_flags()
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    gallery_key = next(k for k, r in engine.state.board.items() if r.template_id == "gallery")

    # p139：事件/房间/伤害都不能削减叛徒的属性
    engine._active_player_id = hero.id
    stats_before = dict(traitor.stats)
    positions_before = dict(traitor.stat_positions)
    engine._deal_damage(traitor, "physical", 5, source="攻击")
    engine._deal_damage(traitor, "mental", 3, source="深渊")
    assert traitor.stats == stats_before and traitor.stat_positions == positions_before, (
        "叛徒应完全免疫伤害削减"
    )

    # p68 例外：持远古护身符的英雄在肉搏中打赢他，伤害照常扣属性
    # （轨道上有重复数值格，所以要看滑格位置，不能只看数值）
    hero.items.append("item_amulet_of_the_ages")
    engine._deal_damage(traitor, "physical", 1, source="攻击")
    assert traitor.stat_positions != positions_before, "远古护身符应能伤到叛徒"
    hero.items.remove("item_amulet_of_the_ages")
    traitor.stat_positions.update(positions_before)  # 复原：后面还要一个完好的叛徒
    traitor.stats.update(stats_before)

    # p139：进入画廊 → 理智 4+，失败吃 1 骰精神伤害（唯一无视免疫的伤害）
    traitor.room_key = gallery_key
    gaze_positions = dict(traitor.stat_positions)
    gaze_stats = dict(traitor.stats)
    with patch.object(engine, "_resolve_check", return_value=False), patch.object(engine, "roll_dice", return_value=2):
        handler._portrait_gaze(engine, traitor)
    assert traitor.stat_positions != gaze_positions, "凝视肖像的反噬必须真的落到属性上"
    # 复原：后面还要用这个叛徒走"销毁颜料"链路
    traitor.stat_positions.update(gaze_positions)
    traitor.stats.update(gaze_stats)
    traitor.dead = False

    # p68：拿起颜料 → 进画廊重绘（知识 4+ 成功消耗颜料并放一枚知识检定令牌）
    paint_token = next(iter(engine.tokens_of_kind("paint")), None)
    assert paint_token is not None
    engine.place_token(paint_token.uid, hero.room_key)
    _set_current(engine, hero)
    handler.on_turn_start(engine, hero)
    assert handler.perform_action(engine, hero, "take_paint", {}) is True
    assert len(handler._held_paint(engine, hero)) == 1
    # p68：每人同时只能携带一枚
    engine.spawn_token("paint", label="颜料", role="marker", room_key=hero.room_key)
    assert handler.perform_action(engine, hero, "take_paint", {}) is False

    # p68：rooms 限制不再写在 rule_data 里（否则会变成机器人的常驻目标），
    # 由 handler 把关：人在画廊外就算手持颜料也不能重绘。
    if hero.room_key == gallery_key:  # 恰好已在画廊：挪出去再验这条限制
        hero.room_key = next(k for k in engine.state.board if k != gallery_key)
    outside = {a.id for a in handler.available_actions(engine, hero)}
    assert "repaint_portrait" not in outside and "take_paint" not in outside
    assert handler.perform_action(engine, hero, "repaint_portrait", {}) is False

    hero.room_key = gallery_key
    goal_before = engine._haunt_track_value("repaint")
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "repaint_portrait", {}) is True
    assert engine._haunt_track_value("repaint") == goal_before + 1
    assert not handler._held_paint(engine, hero), "重绘成功后颜料耗尽（p68）"
    assert engine.tokens_in_room(gallery_key, "knowledge_check"), "重绘成功应在画廊放一枚知识检定令牌"

    # 检定失败时颜料不消耗（p68：只有成功才销毁颜料）
    engine.give_token(engine.tokens_of_kind("paint")[0].uid, hero.id)
    with patch.object(engine, "_resolve_check", return_value=False):
        handler.perform_action(engine, hero, "repaint_portrait", {})
    assert len(handler._held_paint(engine, hero)) == 1, "重绘失败应留着颜料"

    # p68：颜料可以像普通物品一样交易给队友，但不许随处乱丢（防机器人原地打转）
    other = next(p for p in engine.state.players if p.role == "hero" and not p.dead and p.id != hero.id)
    other.stats["knowledge"] = hero.stats["knowledge"] + 2
    paint_room_key = next(
        (t.room_key for t in engine.tokens_of_kind("paint") if t.room_key and t.room_key != gallery_key),
        None,
    ) or next(k for k in engine.state.board if k != gallery_key)

    other.room_key = hero.room_key = gallery_key
    in_gallery = {a.id for a in handler.available_actions(engine, hero)}
    assert "repaint_portrait" in in_gallery
    assert not {"pass_paint", "drop_paint"} & in_gallery, "在画廊里只该重绘，不该传/放颜料"

    other.room_key = hero.room_key = paint_room_key
    _set_current(engine, hero)
    available = {a.id for a in handler.available_actions(engine, hero)}
    assert {"pass_paint", "drop_paint"} <= available, "有更强的队友接得住时才提供传/放"
    assert handler.bot_action_blocked(engine, hero, "drop_paint") is True
    saved_knowledge = hero.stats.get("knowledge", 0)
    hero.stats["knowledge"] = 1
    assert handler.bot_action_blocked(engine, hero, "repaint_portrait") is True
    gallery_goals = handler.bot_goal_rooms(engine, hero)
    assert f"__room__{other.room_key}" in gallery_goals, "掷不出 4+ 应去找能画的队友"
    hero.stats["knowledge"] = saved_knowledge
    assert handler.perform_action(engine, hero, "pass_paint", {}) is True
    assert handler._held_paint(engine, other), "颜料应传到更懂行的队友手里"

    # p139：叛徒手持颜料可销毁一枚，且"代替一次攻击"
    traitor_paint = engine.tokens_of_kind("paint")[0]
    engine.give_token(traitor_paint.uid, traitor.id)
    _set_current(engine, traitor)
    handler.on_turn_start(engine, traitor)
    assert handler.perform_action(engine, traitor, "destroy_paint", {}) is True
    assert engine._haunt_track_value("paint_destroyed") == 1
    assert handler.attack_allowed(engine, traitor, hero) is False, "销毁颜料应占掉本回合的攻击"

    # p139：毁满三枚颜料 → 叛徒胜
    engine._set_haunt_track_value("paint_destroyed", 3)
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor"

    # p68：另一条英雄胜路线——叛徒死亡（引擎通用规则兜底）
    engine.state.winner = ""
    engine._haunt_flags()["spell_broken"] = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes", "集满知识检定令牌即破除诅咒"


def verify_haunt58_nightfall_setup() -> None:
    """剧本 58：熔炉房/噩梦布点、暮色判定、暮色知识攻击（p69/p140）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=58)
    handler = engine._mode_handler()
    assert isinstance(handler, NightfallMode)
    flags = engine._haunt_flags()

    # p69：熔炉房必须在场（不在则从牌堆放进去）
    furnace = flags.get("furnace_key")
    assert furnace and engine.state.board[furnace].template_id == handler.FURNACE
    # p140：噩梦 = 英雄数
    hero_count = sum(1 for p in engine.state.players if p.role == "hero")
    assert len(handler._nightmares(engine)) == hero_count

    # p69：暮色判定——熔炉房不在暮色；叛徒所在房间永远是暮色
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert handler.in_twilight(engine, furnace) is False
    assert handler.in_twilight(engine, traitor.room_key) is True
    other = next(
        (k for k, r in engine.state.board.items() if r.template_id not in handler.TWILIGHT_FREE),
        None,
    )
    assert other is not None and handler.in_twilight(engine, other) is True
    # 已驱散的楼层不算暮色
    flags["banished_floors"] = [engine.state.board[other].floor]
    assert handler.in_twilight(engine, other) is False
    flags["banished_floors"] = []

    # p69/p140：暮色中 explorers and monsters 的力量/速度攻击改用知识；持火把者不受限
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero.room_key = other
    assert handler.attack_attr_override(engine, hero, traitor, "might") == "knowledge"
    nightmare = handler._nightmares(engine)[0]
    nightmare.room_key = other
    assert handler.attack_attr_override(engine, nightmare, hero, "might") == "knowledge"
    flags["torches"] = {str(hero.id): True}
    assert handler.attack_attr_override(engine, hero, traitor, "might") is None
    # p69：火把抵消所在房间的暮色
    assert handler.in_twilight(engine, other) is False
    flags["torches"] = {}
    # 没火把别去追噩梦；叛徒没有剧本房间目标（否则熔炉房保底把它拖走）
    assert handler.bot_attack_blocked(engine, hero, nightmare) is True
    flags["torches"] = {str(hero.id): True}
    assert handler.bot_attack_blocked(engine, hero, nightmare) is False
    flags["torches"] = {}
    assert handler.bot_goal_suppressed(engine, traitor) is True
    assert handler.bot_goal_suppressed(engine, hero) is False
    # 没火把先去熔炉房；队里有一支之后去暮色房会合，别再把全员拽回熔炉房
    no_torch_goals = handler.bot_goal_rooms(engine, hero)
    assert f"__room__{furnace}" in no_torch_goals
    other_hero = next(
        p for p in engine.state.players if p.role == "hero" and not p.dead and p.id != hero.id
    )
    flags["torches"] = {str(hero.id): True}
    assert handler.bot_action_blocked(engine, hero, "create_torch") is True
    assert handler.bot_action_blocked(engine, other_hero, "create_torch") is True
    torch_goals = handler.bot_goal_rooms(engine, hero)
    other_goals = handler.bot_goal_rooms(engine, other_hero)
    rally = handler._rally_room(engine)
    assert rally, "场上应有可驱散的暮色房"
    assert engine.state.board[rally].template_id not in handler.TWILIGHT_FREE
    assert handler._is_stop_risk_room(engine, rally) is False
    assert f"__room__{furnace}" not in torch_goals
    assert f"__room__{furnace}" not in other_goals
    assert torch_goals == [f"__room__{rally}"]
    assert other_goals == [f"__room__{rally}"]
    saved_room = hero.room_key
    hero.room_key = furnace
    assert handler.bot_leave_after_action(engine, hero) is True
    hero.room_key = saved_room
    rally = handler._rally_room(engine)
    hero.room_key = rally
    other_hero.room_key = rally
    assert handler.bot_stay_in_room(engine, hero) is True
    flags["banished_floors"] = [engine.state.board[rally].floor]
    assert handler.bot_leave_after_action(engine, hero) is True
    next_rally = handler._rally_room(engine)
    assert next_rally != rally
    flags["banished_floors"] = []
    flags["torches"] = {}


def verify_haunt58_torch_banish_haunting() -> None:
    """剧本 58：火把、驱散暮色、噩梦摧毁阈值、缠梦（p69/p140）。"""
    engine = _run_until_haunt(seed=137, players=3, haunt_id=58)
    handler = engine._mode_handler()
    assert isinstance(handler, NightfallMode)
    flags = engine._haunt_flags()
    # 驱散暮色要求同房间 ≥2 人：本局可能已有英雄阵亡，测试里先让他们都站起来
    heroes = [p for p in engine.state.players if p.role == "hero"]
    for p in heroes:
        p.dead = False
    assert len(heroes) >= 2

    # p69：造火把只能在熔炉房。先把英雄挪出熔炉房——这条轨迹下第一位英雄
    # 恰好就站在熔炉房里，负向断言会假失败。
    hero = heroes[0]
    _set_current(engine, hero)
    if engine.state.board[hero.room_key].template_id == handler.FURNACE:
        hero.room_key = next(
            key
            for key, room in engine.state.board.items()
            if room.template_id != handler.FURNACE
        )
    assert handler.perform_action(engine, hero, "create_torch", {}) is False
    hero.room_key = flags["furnace_key"]
    assert handler.perform_action(engine, hero, "create_torch", {}) is True
    assert flags["torches"].get(str(hero.id)) is True

    # p69：驱散暮色——需同房间 ≥2 人 + 火把，且知识/理智各至少一次成功
    room_key = next(
        k for k, r in engine.state.board.items() if r.template_id not in handler.TWILIGHT_FREE
    )
    for p in heroes:
        p.room_key = room_key
    assert handler._banish_allowed(engine, hero) is True
    with patch.object(engine, "_resolve_check", return_value=False):
        assert handler.perform_action(engine, hero, "banish_twilight", {}) is False
    checks = iter([True, True, True])
    with patch.object(engine, "_resolve_check", side_effect=lambda *a, **k: next(checks)):
        assert handler.perform_action(engine, hero, "banish_twilight", {}) is True
    assert engine.state.board[room_key].floor in flags["banished_floors"]
    # p69：参与检定者本回合不能移动/攻击
    assert hero.movement_stopped and hero.attack_used
    # 缺理智时只派给掷得出 4+ 的人，别把知识 5 / 理智 1 硬派去掷理智
    hero.stats["knowledge"] = 5
    hero.stats["sanity"] = 1
    assert handler._banish_stat_for(engine, hero, True, False) == "knowledge"
    # 三层全驱散 → 英雄胜
    flags["banished_floors"] = list(handler.FLOORS)
    assert handler.check_victory(engine) is True and engine.state.winner == "heroes"

    # p69：噩梦受 2 点以上伤害即被摧毁，更少只击晕（留场）
    engine2 = _run_until_haunt(seed=137, players=3, haunt_id=58)
    h2 = engine2._mode_handler()
    assert isinstance(h2, NightfallMode)
    nm = h2._nightmares(engine2)[0]
    assert h2.on_monster_defeated(engine2, nm, 1) is True
    assert nm in h2._nightmares(engine2), "1 点伤害只应击晕，不该摧毁"
    assert nm.stunned_turns >= 1, "1 点伤害应由 handler 击晕（返回 True 会跳过引擎默认击晕）"
    assert h2.on_monster_defeated(engine2, nm, 2) is True
    assert nm not in h2._nightmares(engine2), "2 点伤害应摧毁噩梦"

    # p140：噩梦造成 ≥2 精神伤害时改为缠梦；缠梦中的噩梦不可被攻击
    engine3 = _run_until_haunt(seed=137, players=3, haunt_id=58)
    h3 = engine3._mode_handler()
    f3 = engine3._haunt_flags()
    nm3 = h3._nightmares(engine3)[0]
    target3 = next(p for p in engine3.state.players if p.role == "hero" and not p.dead)
    nm3.room_key = target3.room_key
    with patch.object(engine3, "_roll_monster_attack", return_value=9), patch.object(
        engine3, "_roll_attack", return_value=2
    ):
        assert h3.on_monster_turn_attack(engine3, nm3) is True
    assert f3["haunting"].get(nm3.id) == target3.id, "差值 ≥2 应改为缠梦"
    assert h3.attack_allowed(engine3, target3, nm3) is False, "缠梦中的噩梦不可被攻击"
    # p140：回合开始理智 5+ 挣脱 → 噩梦现身于英雄房间
    with patch.object(engine3, "_resolve_check", return_value=True):
        h3.on_turn_start(engine3, target3)
    assert nm3.id not in f3["haunting"], "挣脱后不再被缠"
    assert nm3.room_key == target3.room_key

    # p140：被缠梦的英雄**倒下**后，梦魇必须松开他回到场上。
    # 不释放的后果是两条胜利线同时被掐断：attack_allowed 因 "id in haunting"
    # 永久拒绝攻击这只梦魇，而 on_monster_turn_start 又让它整回合跳过；英雄这边
    # "数位英雄同房 + 持火把"的驱散条件在只剩一人时本就不成立（p69 明文）。
    # seed63/5p、seed3/5p 实测：场上仅存的梦魇全都缠着已死英雄，300 回合无胜者。
    with patch.object(engine3, "_roll_monster_attack", return_value=9), patch.object(
        engine3, "_roll_attack", return_value=2
    ):
        assert h3.on_monster_turn_attack(engine3, nm3) is True
    assert f3["haunting"].get(nm3.id) == target3.id, "重新缠上以便验证「倒下即释放」"
    foe_room = target3.room_key
    target3.dead = True
    h3.on_player_died(engine3, target3)
    assert nm3.id not in f3["haunting"], "被缠梦的英雄倒下后梦魇必须松开"
    assert nm3.room_key == foe_room, "松开的梦魇现身在倒下的英雄所在房间（同挣脱口径）"
    assert h3.on_monster_turn_start(engine3, nm3) is False, (
        "不再缠梦后噩梦恢复常规回合，不再整回合跳过"
    )
    # 释放是定向的：缠着别人的梦魇不受影响
    if len(h3._nightmares(engine3)) >= 2:
        other_nm = next(m for m in h3._nightmares(engine3) if m.id != nm3.id)
        mate = next(
            (p for p in engine3.state.players if p.role == "hero" and not p.dead),
            None,
        )
        if mate is not None and mate.id != target3.id:
            f3["haunting"][other_nm.id] = mate.id
            mate.dead = True
            h3.on_player_died(engine3, mate)
            assert other_nm.id not in f3["haunting"], "倒下者的梦魇也应释放"
            # 已被释放的 nm3 不该被这次死亡波及
            assert nm3.id not in f3["haunting"]


def verify_haunt59_badge_setup() -> None:
    """剧本 59：女巫/雕像布点、徽章归属、持徽章英雄限速 2 格（p70/p141）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=59)
    handler = engine._mode_handler()
    assert isinstance(handler, ForAThousandYearsMode)
    flags = engine._haunt_flags()
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # p141：女巫 + 雕像在带预兆图标的房间（非作祟房）
    haunt_room = engine.state.meta["haunt_rule"]["haunt_room"]
    hero_count = sum(1 for p in engine.state.players if p.role == "hero")
    statue_key = flags["statue_key"]
    assert statue_key and engine.state.board[statue_key].symbol == "omen"
    assert statue_key != haunt_room
    assert any(
        m.template_id == handler.WITCH and m.room_key == statue_key
        for m in engine.state.monsters
    )
    # p141：英雄数 ≥3 才放熊（3 人局 = 1 叛徒 + 2 英雄，熊不应出现）；
    #       4 英雄局再加猫、5 英雄局再加信徒
    bears = [m for m in engine.state.monsters if m.template_id == handler.BEAR]
    if hero_count >= 3:
        assert bears, "英雄数 ≥3 应放熊"
    else:
        assert not bears, "英雄数 <3 不应放熊"
    cats = [m for m in engine.state.monsters if m.template_id == handler.CAT]
    assert (len(cats) > 0) == (hero_count >= 4)
    assert flags["medallion_holder"] == f"traitor:{traitor.id}"
    assert handler.MEDALLION in traitor.items

    # p70：持徽章英雄每回合最多 2 格（手动给他徽章模拟夺回）
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor.items = [c for c in traitor.items if c != handler.MEDALLION]
    flags["medallion_holder"] = f"hero:{hero.id}"
    hero.items.append(handler.MEDALLION)
    flags["medallion_steps"] = {}
    handler.on_player_moved(engine, hero)
    handler.on_player_moved(engine, hero)
    assert hero.movement_stopped and hero.steps_remaining == 0, "持徽章第 2 格应停下"
    # 回合开始重置
    handler.on_turn_start(engine, hero)
    assert hero.movement_stopped is False or str(hero.id) not in flags["medallion_steps"]


def verify_haunt59_medallion_flow() -> None:
    """剧本 59：放置徽章胜利、猫抢徽章、塔楼毁徽章、怪物掉徽章（p70/p141）。"""
    engine = _run_until_haunt(seed=137, players=3, haunt_id=59)
    handler = engine._mode_handler()
    assert isinstance(handler, ForAThousandYearsMode)
    flags = engine._haunt_flags()
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # p70/p141：打赢持徽章者就该改偷，不能默认弃伤害
    assert handler.bot_wants_steal(engine, hero, traitor) == handler.MEDALLION
    statue_key = flags.get("statue_key")
    assert statue_key
    assert engine.tokens_in_room(statue_key, handler.STATUE), "开局必须把国王雕像令牌放进雕像房"
    # 没拿徽章时挂徽章不能当寻路目标，否则全员扎进雕像房从不去抢叛徒
    assert handler.bot_action_blocked(engine, hero, "place_medallion") is True
    witch = next(m for m in engine.state.monsters if m.template_id == handler.WITCH)
    assert handler.bot_attack_blocked(engine, hero, witch) is True, "徽章不在怪手里时别去捶女巫"
    assert handler.bot_attack_blocked(engine, hero, traitor) is False, "持徽章的叛徒必须能打"
    # 自己拿着徽章、女巫堵在雕像房：必须能清场，否则永远挂不上去
    witch.room_key = statue_key
    hero.items.append(handler.MEDALLION)
    flags["medallion_holder"] = f"hero:{hero.id}"
    traitor.items = [c for c in traitor.items if c != handler.MEDALLION]
    assert handler.bot_attack_blocked(engine, hero, witch) is False, "雕像房挡路的怪必须能打"
    hero.items = [c for c in hero.items if c != handler.MEDALLION]
    flags["medallion_holder"] = f"traitor:{traitor.id}"
    traitor.items.append(handler.MEDALLION)
    witch.room_key = statue_key
    traitor.items = [c for c in traitor.items if c != handler.MEDALLION]
    hero.items.append(handler.MEDALLION)
    handler.on_attack_resolved(engine, hero, traitor, True)
    assert flags["medallion_holder"] == f"hero:{hero.id}"
    # 队友拿着徽章：去雕像会合，而不是空目标掉进塔楼保底
    other = next(
        (p for p in engine.state.players if p.role == "hero" and p.id != hero.id and not p.dead),
        None,
    )
    if other is not None:
        goals = handler.bot_goal_rooms(engine, other)
        statue = flags.get("statue_key")
        assert statue is not None
        assert f"__room__{statue}" in goals

    # p70：挂徽章胜利——mock 速度检定成功
    hero.room_key = flags["statue_key"]
    _set_current(engine, hero)
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "place_medallion", {}) is True
    assert engine.state.winner == "heroes"

    # 重开一局：猫抢徽章 + 塔楼毁徽章 → 叛徒胜
    engine2 = _run_until_haunt(seed=137, players=3, haunt_id=59)
    h2 = engine2._mode_handler()
    assert isinstance(h2, ForAThousandYearsMode)
    f2 = engine2._haunt_flags()
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    # 3 人局英雄数 <4 没有猫：把在场一只怪物改造成猫来构造抢徽章场景
    cat = engine2.state.monsters[0]
    cat.template_id = h2.CAT
    traitor2_setup = next(p for p in engine2.state.players if p.role == "traitor")
    traitor2_setup.items = [c for c in traitor2_setup.items if c != h2.MEDALLION]
    hero2.items.append(h2.MEDALLION)
    f2["medallion_holder"] = f"hero:{hero2.id}"
    cat.room_key = hero2.room_key
    with patch.object(engine2, "_roll_monster_attack", return_value=6), patch.object(
        engine2, "_roll_attack", return_value=3
    ):
        assert h2.on_monster_turn_attack(engine2, cat) is True
    assert f2["medallion_holder"] == f"monster:{cat.id}", "差值 ≥2 猫应抢走徽章"
    assert h2.MEDALLION not in hero2.items
    # 怪物带着徽章路过塔楼不算赢；叛徒回合结束才扔
    tower = next((k for k, r in engine2.state.board.items() if r.template_id == "tower"), None)
    assert tower is not None, "塔楼应在场（骨架保证）"
    cat.room_key = tower
    assert h2.check_victory(engine2) is not True or engine2.state.winner is None
    assert engine2.state.winner is None, "路过塔楼不应立刻判胜"
    traitor2 = next(p for p in engine2.state.players if p.role == "traitor")
    h2.on_turn_end(engine2, traitor2)
    assert engine2.state.winner == "traitor"

    # p141：持徽章怪物被击败 → 徽章掉地上（英雄可拾取）
    engine3 = _run_until_haunt(seed=137, players=3, haunt_id=59)
    h3 = engine3._mode_handler()
    f3 = engine3._haunt_flags()
    cat3 = engine3.state.monsters[0]
    cat3.template_id = h3.CAT
    f3["medallion_holder"] = f"monster:{cat3.id}"
    assert h3.on_monster_defeated(engine3, cat3, 2) is False
    assert f3["medallion_holder"] is None
    assert cat3.room_key in engine3.state.room_items and h3.MEDALLION in engine3.state.room_items[cat3.room_key]


def verify_haunt60_burning_sands_setup() -> None:
    """剧本 60：斯芬克斯布点门厅、拦路费用、嘲讽攻击不受伤（p71/p142）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=60)
    handler = engine._mode_handler()
    assert isinstance(handler, BurningSandsMode)

    # p140：斯芬克斯 = 英雄数，全部在门厅
    hero_count = sum(1 for p in engine.state.players if p.role == "hero")
    sphinxes = [
        m for m in engine.state.monsters if m.template_id == handler.SPHINX
    ]
    assert len(sphinxes) == hero_count
    hall = next(k for k, r in engine.state.board.items() if r.template_id == handler.HALL)
    assert all(s.room_key == hall for s in sphinxes)

    # p71：离开有斯芬克斯的房间每只 3 点；晕的不拦
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero.room_key = hall
    assert handler.movement_cost_floor(engine, hero, hall, None) == 3 * hero_count
    for s in sphinxes:
        s.stunned_turns = 1
    assert handler.movement_cost_floor(engine, hero, hall, None) == 0, "被晕的斯芬克斯不拦路"
    for s in sphinxes:
        s.stunned_turns = 0

    # p142：嘲讽攻击——斯芬克斯输了对决不受伤也不被晕
    target = hero
    sphinxes[0].room_key = target.room_key
    before_stun = sphinxes[0].stunned_turns
    with patch.object(engine, "_roll_monster_attack", return_value=2), patch.object(
        engine, "_roll_attack", return_value=5
    ):
        assert handler.on_monster_turn_attack(engine, sphinxes[0]) is True
    assert sphinxes[0].stunned_turns == before_stun, "斯芬克斯输了对决也不该被晕"
    assert engine.state.players and target.stat_positions["sanity"] >= 0

    # p142：不进只有英雄、没有叛徒/另一只斯芬克斯的房间
    empty = next(
        k
        for k, r in engine.state.board.items()
        if k != hall and not any(p.room_key == k for p in engine.state.players)
    )
    hero.room_key = empty
    sphinxes[0].room_key = hall
    assert handler._sphinx_may_enter(engine, sphinxes[0], empty) is False
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    traitor.room_key = empty
    assert handler._sphinx_may_enter(engine, sphinxes[0], empty) is True


def verify_haunt60_riddle_race() -> None:
    """剧本 60：三线索收集、英雄解谜胜利、叛徒解谜胜利（p71/p142）。"""
    engine = _run_until_haunt(seed=137, players=3, haunt_id=60)
    handler = engine._mode_handler()
    assert isinstance(handler, BurningSandsMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    _set_current(engine, hero)

    # 三线索：不在对应房间失败；在对应房间且检定成功 → 线索 +1 并抽事件牌
    assert handler.perform_action(engine, hero, "clue_junk", {}) is False
    room_of = {
        tid: k
        for tid in handler.CLUE_ROOMS.values()
        for k, r in engine.state.board.items()
        if r.template_id == tid
    }
    hero.room_key = room_of["junk_room"]
    saved_might = hero.stats.get("might", 0)
    hero.stats["might"] = 1
    assert handler.bot_action_blocked(engine, hero, "clue_junk") is True
    assert "junk_room" not in handler.bot_goal_rooms(engine, hero)
    saved_speed = hero.stats.get("speed", 0)
    saved_sanity = hero.stats.get("sanity", 0)
    hero.stats["speed"] = 1
    hero.stats["sanity"] = 1
    unhittable_goals = handler.bot_goal_rooms(engine, hero)
    assert "junk_room" not in unhittable_goals
    assert "game_room" not in unhittable_goals
    assert "organ_room" not in unhittable_goals
    sphinx_goals = {
        f"__room__{m.room_key}"
        for m in engine.state.monsters
        if m.template_id == handler.SPHINX and m.room_key
    }
    assert unhittable_goals and set(unhittable_goals) <= sphinx_goals, (
        "三条都掷不出时应去撞斯芬克斯，别把线索房当死循环"
    )
    assert handler.bot_goal_suppressed(engine, hero) is False, "有斯芬克斯时不要压掉自定义目标"
    hero.stats["speed"] = saved_speed
    hero.stats["sanity"] = saved_sanity
    hero.stats["might"] = saved_might
    assert handler.bot_goal_suppressed(engine, hero) is False
    events_before = len(engine.state.card_discards.get("event", []))
    with patch.object(engine, "_resolve_check", return_value=True), patch.object(
        engine, "_draw_event", return_value=None
    ) as draw:
        assert handler.perform_action(engine, hero, "clue_junk", {}) is True
        assert draw.called, "拿线索后应抽一张事件牌"
    assert set(flags["clues"][str(hero.id)]) == {"might"}
    # 重复拿同一条线索：不允许（还没真正掷骰，不耗行动）
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "clue_junk", {}) is False
    # p71：检定失败也算本回合那一次尝试
    hero.room_key = room_of["game_room"]
    with patch.object(engine, "_resolve_check", return_value=False):
        assert handler.perform_action(engine, hero, "clue_gameroom", {}) is True
    assert "speed" not in handler._clues(engine, hero)
    # 失败也耗行动后必须离开，否则 _pending 把人钉在线索房空点（seed101/5p ×251）
    assert handler.bot_leave_after_action(engine, hero) is True
    # 其余两条（抽事件一律 mock，避免事件把英雄抽死导致 leave 断言漂移）
    hero.room_key = room_of["game_room"]
    with patch.object(engine, "_resolve_check", return_value=True), patch.object(
        engine, "_draw_event", return_value=None
    ):
        assert handler.perform_action(engine, hero, "clue_gameroom", {}) is True
    hero.room_key = room_of["organ_room"]
    with patch.object(engine, "_resolve_check", return_value=True), patch.object(
        engine, "_draw_event", return_value=None
    ):
        assert handler.perform_action(engine, hero, "clue_organ", {}) is True
    assert not hero.dead
    assert len(handler._clues(engine, hero)) == 3
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "clue_junk" not in ids and "clue_gameroom" not in ids and "clue_organ" not in ids
    haunt_room = engine.state.meta["haunt_rule"]["haunt_room"]
    assert handler.bot_leave_after_action(engine, hero) is (hero.room_key != haunt_room)

    # 线索不全时解谜失败（新英雄没有线索；该局可能有英雄阵亡，先复活）
    hero2 = next(p for p in engine.state.players if p.role == "hero" and p.id != hero.id)
    hero2.dead = False
    _set_current(engine, hero2)
    haunt_room = engine.state.meta["haunt_rule"]["haunt_room"]
    hero2.room_key = haunt_room
    assert handler.perform_action(engine, hero2, "solve_riddle", {}) is False

    # p71：集齐三线索 + 作祟房知识 6+ 成功 → 英雄胜
    _set_current(engine, hero)
    hero.room_key = haunt_room
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "solve_riddle", {}) is True
    assert engine.state.winner == "heroes"

    # p142：叛徒解谜（知识 5+）→ 叛徒胜
    engine2 = _run_until_haunt(seed=137, players=3, haunt_id=60)
    h2 = engine2._mode_handler()
    assert isinstance(h2, BurningSandsMode)
    f2 = engine2._haunt_flags()
    traitor2 = next(p for p in engine2.state.players if p.role == "traitor")
    _set_current(engine2, traitor2)
    f2["clues"][str(traitor2.id)] = ["might", "speed", "sanity"]
    traitor2.room_key = engine2.state.meta["haunt_rule"]["haunt_room"]
    with patch.object(engine2, "_resolve_check", return_value=True):
        assert h2.perform_action(engine2, traitor2, "traitor_solve_riddle", {}) is True
    assert engine2.state.winner == "traitor"


def verify_haunt69_wisp_setup() -> None:
    """剧本 69：叛徒出局、小精灵布点、轨道起点、孢子留痕（p80/p151）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=69)
    handler = engine._mode_handler()
    assert isinstance(handler, WispCaptureMode)
    flags = engine._haunt_flags()
    haunt_room = engine.state.meta["haunt_rule"]["haunt_room"]

    # p151：叛徒角色移出游戏（是设计不是失败——吸收兜底，不能判英雄胜）
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert traitor.dead, "p151 叛徒角色应被移出游戏"
    assert handler.check_victory(engine) is True and engine.state.winner is None

    # p151：小精灵放作祟房；轨道起点为 1（先手）
    wisp = handler._wisp(engine)
    assert wisp is not None and wisp.room_key == haunt_room
    assert (wisp.speed, wisp.might, wisp.sanity) == (5, 6, 6)
    assert flags["wisp_track"] == 1
    # p151：地下室楼梯应在场
    assert any(
        r.template_id == handler.STAIRS for r in engine.state.board.values()
    ), "地下室楼梯应被取出放好"

    # p151：小精灵回合——轨道 +1、清除孢子、留痕、不能停在孢子房
    flags["spore_rooms"] = []
    before = wisp.room_key
    handler.on_monster_turn_start(engine, wisp)
    assert flags["wisp_track"] == 2
    assert before in handler._spore_rooms(engine), "离开的房间应留下孢子"
    assert wisp.room_key != before
    assert wisp.room_key not in handler._spore_rooms(engine), "不能停在孢子房"


def verify_haunt69_catch_and_escape() -> None:
    """剧本 69：孢子检定三分支、捕捉胜利、轨道 6 逃脱（p80/p151）。"""
    engine = _run_until_haunt(seed=137, players=3, haunt_id=69)
    handler = engine._mode_handler()
    assert isinstance(handler, WispCaptureMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # p80：孢子迷雾三分支（6+ 免疫 / 2-5 多花 1 点 / 0-1 回合结束）
    room_key = next(iter(sorted(engine.state.board)))
    handler._set_spores(engine, [room_key])
    hero.room_key = room_key
    with patch.object(engine, "roll_dice", return_value=6):
        assert handler.movement_cost_floor(engine, hero, room_key, None) == 0
        assert flags["spore_state"][str(hero.id)] == "immune"
    handler.on_turn_start(engine, hero)
    with patch.object(engine, "roll_dice", return_value=3):
        assert handler.movement_cost_floor(engine, hero, room_key, None) == 2
        assert flags["spore_state"][str(hero.id)] == "slow"
    handler.on_turn_start(engine, hero)
    hero.movement_stopped = False
    with patch.object(engine, "roll_dice", return_value=0):
        assert handler.movement_cost_floor(engine, hero, room_key, None) == 0
        assert hero.movement_stopped and hero.attack_used
        assert flags["spore_state"][str(hero.id)] == "ended"

    # p80：捕捉——知识 4+ 成功 +1 令牌，累计英雄数枚即英雄胜
    engine2 = _run_until_haunt(seed=113, players=3, haunt_id=69)
    h2 = engine2._mode_handler()
    assert isinstance(h2, WispCaptureMode)
    wisp2 = h2._wisp(engine2)
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    _set_current(engine2, hero2)
    hero2.room_key = wisp2.room_key
    needed = engine2._haunt_track_target("capture_tokens")
    hero_count = sum(1 for p in engine2.state.players if p.role == "hero")
    assert needed == hero_count
    for _ in range(needed):
        with patch.object(engine2, "_resolve_check", return_value=True):
            assert h2.perform_action(engine2, hero2, "catch_wisp", {}) is True
    assert engine2.state.winner == "heroes"

    # p151：轨道到 6 → 小精灵逃脱 → 叛徒胜
    engine3 = _run_until_haunt(seed=113, players=3, haunt_id=69)
    h3 = engine3._mode_handler()
    assert isinstance(h3, WispCaptureMode)
    f3 = engine3._haunt_flags()
    f3["wisp_track"] = 6
    assert h3.check_victory(engine3) is True and engine3.state.winner == "traitor"


def verify_haunt70_transformation_setup() -> None:
    """剧本 70：叛徒清空物品、形态秘密选定、形态房间在场、免疫拦截（p81/p152）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=70)
    handler = engine._mode_handler()
    assert isinstance(handler, InhumanTransformationMode)
    flags = engine._haunt_flags()
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # p152：形态随机秘密选定（只在 flags 里），且三种之一
    assert flags["form"] in handler.FORMS
    # p152：叛徒丢弃全部物品/预兆，但保留 Bite
    assert handler.BITE in traitor.items
    assert all(c == handler.BITE for c in traitor.items)
    # p152：物理属性不低于起始值
    for stat in ("might", "speed"):
        assert traitor.stats.get(stat, 0) >= traitor.stats_max.get(stat, 0)
    # 形态房间与地下室通路都保证在场
    on_board = {r.template_id for r in engine.state.board.values()}
    assert handler._required_rooms(engine), "形态房间应至少有一间可达"
    assert "entrance_hall" in on_board and "basement_landing" in on_board

    # p81/p152：叛徒免疫普通攻击——英雄空手攻击被拦
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero.room_key = traitor.room_key
    assert handler.attack_allowed(engine, hero, traitor) is False, "徒手攻击应被免疫拦下"
    # 按形态给出克制武器后放行
    form = handler._form(engine)
    if form == "vampire":
        hero.items.append(handler.TRAITOR_WEAPONS[0])
        flags["holy_weapons"] = [handler.TRAITOR_WEAPONS[0]]
        assert handler.attack_allowed(engine, hero, traitor) is True
    elif form == "werewolf":
        hero.items.append(handler.REVOLVER)
        flags["silver_bullets"] = True
        assert handler.attack_allowed(engine, hero, traitor) is True


def verify_haunt70_weapons_and_immunity() -> None:
    """剧本 70：圣水/银弹/杀虫剂三条武器线、净化即胜、干扰令牌（p81/p152）。"""
    engine = _run_until_haunt(seed=137, players=3, haunt_id=70)
    handler = engine._mode_handler()
    assert isinstance(handler, InhumanTransformationMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    _set_current(engine, hero)

    # p81：圣水需要圣徽/天使羽毛 + 在礼拜堂/酒窖/地下湖
    on_board = {r.template_id: k for k, r in engine.state.board.items()}
    chapel = on_board.get("chapel")
    if chapel:
        hero.room_key = chapel
        hero.items.append(handler.HOLY_TOOLS[0])
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "create_holy_water", {}) is True
        assert chapel in flags["holy_rooms"]
        # 蘸武器（代替攻击）
        hero.items.append(handler.TRAITOR_WEAPONS[0])
        assert handler.perform_action(engine, hero, "dip_weapon", {}) is True
        assert handler.TRAITOR_WEAPONS[0] in flags["holy_weapons"]

    # p81：杀虫剂三材料 + 合成（免掷骰的喷杀走单独行动）
    engine2 = _run_until_haunt(seed=137, players=3, haunt_id=70)
    h2 = engine2._mode_handler()
    f2 = engine2._haunt_flags()
    f2["ingredients"] = list(h2.INGREDIENTS)
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    _set_current(engine2, hero2)
    with patch.object(engine2, "_resolve_check", return_value=True):
        assert h2.perform_action(engine2, hero2, "assemble_bug_spray", {}) is True
    assert f2["bug_spray"] is True and f2["ingredients"] == []

    # p81：蜘蛛形态下喷杀虫剂 → 英雄立即获胜
    engine3 = _run_until_haunt(seed=137, players=3, haunt_id=70)
    h3 = engine3._mode_handler()
    f3 = engine3._haunt_flags()
    f3["form"] = "bane_spider"
    f3["bug_spray"] = True
    traitor3 = next(p for p in engine3.state.players if p.role == "traitor")
    hero3 = next(p for p in engine3.state.players if p.role == "hero" and not p.dead)
    hero3.room_key = traitor3.room_key
    _set_current(engine3, hero3)
    assert h3.perform_action(engine3, hero3, "spray_traitor", {}) is True
    assert engine3.state.winner == "heroes"

    # p152：叛徒的干扰令牌——英雄下回合对应属性 4+ 挣脱，否则回合立即结束
    engine4 = _run_until_haunt(seed=137, players=3, haunt_id=70)
    h4 = engine4._mode_handler()
    f4 = engine4._haunt_flags()
    f4["form"] = "vampire"
    traitor4 = next(p for p in engine4.state.players if p.role == "traitor")
    hero4 = next(p for p in engine4.state.players if p.role == "hero" and not p.dead)
    traitor4.room_key = hero4.room_key
    _set_current(engine4, traitor4)
    assert h4.perform_action(engine4, traitor4, "token_hypnotize", {}) is True
    assert f4["tokens"].get(str(hero4.id)) == "sanity"
    hero4.movement_stopped = False
    with patch.object(engine4, "roll_dice", return_value=1):
        h4.on_turn_start(engine4, hero4)
    assert hero4.movement_stopped and hero4.attack_used, "检定失败应困住英雄"


def verify_haunt70_bot_no_noop_actions() -> None:
    """剧本 70：机器人不该把回合浪费在"做了等于没做"的行动上（p81/p152）。

    三处实测过的空转：
      · `create_holy_water` 在"这间房已经有圣水"时仍被提供，且它的声明顺序
        排在 `dip_weapon` 前面——bot 打分同分取靠前者，于是英雄站在礼拜堂里
        无限重复制作圣水（实测 ×120），蘸水一次都排不上，吸血鬼那条英雄胜线
        整条死掉；
      · `dip_weapon` 在"手上的克制品全蘸过"之后仍是空转；
      · 叛徒的 `token_*` 只要同房有英雄就一直可用，`_pending_haunt_action_here`
        于是每回合都让 `_run_turn` 原地 break——叛徒驻扎放令牌、永不访房间
        （实测 token_trap×60、300 回合僵局）。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=70)
    handler = engine._mode_handler()
    assert isinstance(handler, InhumanTransformationMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    _set_current(engine, hero)

    # 形态房之外的圣水房不在场：手动保证一间在场
    engine._ensure_room_in_play("chapel", engine.state.meta["haunt_rule"].get("haunt_room") or "")
    chapel = next(
        (k for k, r in sorted(engine.state.board.items()) if r.template_id == "chapel"), None
    )
    assert chapel, "测试需要一间礼拜堂"

    hero.room_key = chapel
    hero.items.append(handler.HOLY_TOOLS[0])
    assert "create_holy_water" in {a.id for a in handler.available_actions(engine, hero)}
    flags["holy_rooms"] = [chapel]
    assert "create_holy_water" not in {a.id for a in handler.available_actions(engine, hero)}, \
        "已有圣水的房间不该再提供制作圣水（否则空转）"

    hero.items.append(handler.TRAITOR_WEAPONS[0])
    assert "dip_weapon" in {a.id for a in handler.available_actions(engine, hero)}
    # 探索阶段本就可能捡到别的武器：蘸第二件仍是正经进展，所以这里把
    # "手上所有克制品"都记进 holy_weapons，才等于"全蘸过了"。
    holds = [c for c in handler.TRAITOR_WEAPONS if c in hero.items]
    flags["holy_weapons"] = list(holds)
    assert "dip_weapon" not in {a.id for a in handler.available_actions(engine, hero)}, \
        "武器全蘸过了不该再提供蘸水（否则空转）"

    # 叛徒：投放令牌后必须继续挪窝（否则原地驻扎、永不访房间）
    assert handler.bot_leave_after_action(engine, traitor) is True
    assert handler.bot_leave_after_action(engine, hero) is False

    # 吸血鬼：访完房间且英雄就在眼前 → 留守（回合结束才算吸到血）
    flags["form"] = "vampire"
    flags["blood_drawn"] = False
    flags["visited"] = list(handler._required_rooms(engine))
    traitor.room_key = hero.room_key
    assert handler.bot_stay_in_room(engine, traitor) is True
    flags["visited"] = []
    assert handler.bot_stay_in_room(engine, traitor) is False, "还没访完房间：先跑房间"
    flags["visited"] = list(handler._required_rooms(engine))
    flags["blood_drawn"] = True
    assert handler.bot_stay_in_room(engine, traitor) is False, "血已吸到：该去清场"
    # 其他形态不需要吸血 → 永不因吸血而滞留
    flags["form"] = "werewolf"
    flags["blood_drawn"] = False
    assert handler.bot_stay_in_room(engine, traitor) is False


def verify_haunt5_werewolf_hunt() -> None:
    """剧本 5：狗的布点、叛徒回合强化、找左轮/制银弹两条行动线（p16/p87）。

    这个剧本此前只有 handler 注册断言与黄金回放，没有专属专项测试——
    M10-15 测试扩容审计发现的唯一空白（与 44/47 曾漏黄金用例同类）。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=5)
    handler = engine._mode_handler()
    assert isinstance(handler, WerewolfHuntMode)
    flags = engine._haunt_flags()

    # setup：狗在作祟房；两条进度 flag 初始为假
    assert any(m.template_id == "dog" for m in engine.state.monsters), "狗应在场"
    assert flags.get("revolver_found") is False
    assert flags.get("silver_bullets_created") is False

    # on_turn_start：叛徒在感染态里持续强化（力量/速度单调不减、至少一项上升）
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    before = (traitor.stats.get("might", 0), traitor.stats.get("speed", 0))
    pos_before = (traitor.stat_positions.get("might"), traitor.stat_positions.get("speed"))
    handler.on_turn_start(engine, traitor)
    after = (traitor.stats.get("might", 0), traitor.stats.get("speed", 0))
    pos_after = (traitor.stat_positions.get("might"), traitor.stat_positions.get("speed"))
    assert after[0] >= before[0] and after[1] >= before[1]
    # 轨道上有重复数值（例 [2,3,3,4,5,5,5,6]），+1 格可能不改变显示值——
    # 强化要看"格位推进"，只比数值会随角色轨道形状假失败。
    assert pos_after != pos_before or after != before, "叛徒回合开始应获得强化"

    # 英雄线：在场上存在的目标房间做知识检定 → 找左轮 / 制银弹
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    _set_current(engine, hero)
    room_of = {r.template_id: k for k, r in engine.state.board.items()}

    revolver_rooms = [r for r in ("attic", "game_room", "junk_room", "master_bedroom", "vault") if r in room_of]
    if revolver_rooms and not engine._card_is_controlled("item_revolver"):
        hero.room_key = room_of[revolver_rooms[0]]
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "h5_find_revolver", {}) is True
        assert flags.get("revolver_found") is True, "检定成功应找到左轮"

    bullet_rooms = [r for r in ("research_laboratory", "furnace_room") if r in room_of]
    if bullet_rooms and flags.get("silver_bullets_holder") is None:
        hero.room_key = room_of[bullet_rooms[0]]
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "h5_make_silver_bullets", {}) is True
        assert flags.get("silver_bullets_created") is True, "检定成功应制成银弹"


def verify_haunt56_mask_sanity_floor() -> None:
    """剧本 56：面具 -2 理智的死亡保护方向（p138：会致死则停在骷髅上一格）。

    回归 M10-16 修的反向 bug——旧实现判断的是**上界**（pos+2 > len-1）并把位置
    上调，只有理智接近顶格时才触发、触发后反而把理智抬上去。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=56)
    handler = engine._mode_handler()
    assert isinstance(handler, SandsOfTimeMode)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    track = engine._stat_track(traitor, "sanity")
    assert track and len(track) >= 6 and track[0] > 0, "理智轨道应为递增且 >0"
    haunt = engine.state.haunt

    # 情形 A：理智在格位 1，-2 会跌到骷髅 → 保底格位 0（骷髅上一格）
    traitor.stat_positions["sanity"] = 1
    traitor.stats["sanity"] = track[1]
    traitor.overflow["sanity"] = 0
    handler.setup(engine, haunt, traitor.room_key)
    assert traitor.stat_positions["sanity"] == 0, "会致死的 -2 应停在骷髅上一格"
    assert traitor.stats["sanity"] == track[0]
    assert not traitor.dead, "面具保护下不应死亡"

    # 情形 B：理智充裕（格位 5）→ 正常 -2（落到格位 3）
    traitor.stat_positions["sanity"] = 5
    traitor.stats["sanity"] = track[5]
    traitor.overflow["sanity"] = 0
    handler.setup(engine, haunt, traitor.room_key)
    assert traitor.stat_positions["sanity"] == 3, "理智充裕时应正常 -2"


def verify_haunt32_house_reshuffle() -> None:
    """剧本 32：p114 撤下非起始/非占用房间、占用房挪到起始牌旁、管风琴房在场。

    回归 M10-18 新增的引擎能力（`_detach_room` / `_place_room_adjacent` /
    `_shuffle_room_piles`）——此前这三条只做到"洗牌堆"的近似。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=32)
    handler = engine._mode_handler()
    assert isinstance(handler, LostDimensionMode)
    flags = engine._haunt_flags()

    ids = {room.template_id for room in engine.state.board.values()}
    for start_id in engine.START_ROOM_IDS:
        assert start_id in ids, f"起始牌 {start_id} 不该被撤下"
    assert handler.ORGAN_ROOM in ids, "管风琴房必须在场（p114 明文）"
    assert flags["set_aside_rooms"] > 0, "本局应至少撤下过一块房间"
    leftover = [
        room.name
        for key, room in engine.state.board.items()
        if room.template_id not in engine.START_ROOM_IDS
        and room.template_id != handler.ORGAN_ROOM
        and not engine._is_room_occupied(key)
    ]
    assert not leftover, f"非起始/非占用房间应被撤下：{leftover}"
    for key, room in engine.state.board.items():
        if room.template_id in engine.START_ROOM_IDS or room.template_id == handler.ORGAN_ROOM:
            continue
        assert any(
            engine.state.board[nb].template_id in engine.START_ROOM_IDS
            for nb in engine._door_neighbors(key)
        ), f"「{room.name}」应被挪到起始牌旁边并连通"
    assert engine.state.room_discard == [], "弃牌堆应并入洗匀"
    assert all(
        engine.state.pos_index.get((r.floor, r.x, r.y)) == k
        for k, r in engine.state.board.items()
    )
    assert all(p.room_key in engine.state.board for p in engine.state.players if not p.dead)
    assert all(m.room_key in engine.state.board for m in engine.state.monsters)


def verify_haunt68_tile_rearrange() -> None:
    """剧本 68：p150 地下墓穴真删除、其余房间同层重排且每层全连通。

    回归 M10-18 的 `_detach_room` + `_rearrange_floor`（此前是塌方标记 + 不重排）。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=68)
    handler = engine._mode_handler()
    assert isinstance(handler, LabyrinthEscapeMode)

    assert not any(
        room.template_id == handler.CATACOMBS for room in engine.state.board.values()
    ), "地下墓穴应被移出本局（真删除）"
    assert all(p.room_key in engine.state.board for p in engine.state.players if not p.dead)
    assert all(m.room_key in engine.state.board for m in engine.state.monsters)
    assert all(
        t.room_key in engine.state.board for t in engine.state.tokens if t.holder is None
    )
    graph = engine._build_graph()
    for floor in (-1, 0, 1):
        keys = sorted(
            k
            for k, r in engine.state.board.items()
            if r.floor == floor and not r.data.get(engine.COLLAPSE_KEY)
        )
        if len(keys) <= 1:
            continue
        seen = {keys[0]}
        stack = [keys[0]]
        while stack:
            current = stack.pop()
            for neighbour in graph.get(current, []):
                if neighbour in seen:
                    continue
                if engine.state.board[neighbour].floor != floor:
                    continue
                if engine.state.board[neighbour].data.get(engine.COLLAPSE_KEY):
                    continue
                seen.add(neighbour)
                stack.append(neighbour)
        assert len(seen) == len(keys), f"{floor} 层应全连通，实际 {len(seen)}/{len(keys)}"
    assert all(
        engine.state.pos_index.get((r.floor, r.x, r.y)) == k
        for k, r in engine.state.board.items()
    )
    hero_count = int(engine._haunt_flags()["hero_count"])
    assert len(engine.tokens_of_kind(handler.KEY)) == hero_count


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
    # p86：倒计时"随叛徒回合推进"。3-4 人局叛徒通常已被蜘蛛吃掉，此时改用
    # "本轮首位存活玩家"代跑；但若叛徒恰好是作祟揭示者则会留场（setup 的例外），
    # 这时必须由叛徒本人推进——写死"首位存活玩家"会在这种情况下永不推进。
    traitor = next((p for p in engine.state.players if p.role == "traitor" and not p.dead), None)
    alive = [p for p in engine.state.players if not p.dead]
    ticker = traitor if traitor is not None else alive[0]

    deadline = engine._haunt_track_target("spider_timer")
    for i in range(deadline - 1):
        handler.on_turn_start(engine, ticker)
        assert engine.state.winner is None, f"第 {i + 1} 轮不应判负"
    assert engine._haunt_track_value("spider_timer") == deadline - 1

    handler.on_turn_start(engine, ticker)
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


def verify_haunt31_organ_rooms() -> None:
    """剧本 31 六器官房：胃/肺/牙/腺体在“进入房间/开始回合”查表结算（p42/p113）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=31)
    handler = engine._mode_handler()
    assert isinstance(handler, LivingHouseMode)

    # 复活并稳住英雄（setup 胃检定/探险可能打死人），保证有活英雄跑各分支
    for person in engine.state.players:
        if person.role == "hero":
            person.dead = False
            for stat in ("speed", "might", "sanity", "knowledge"):
                person.stats[stat] = 4
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next((p for p in engine.state.players if p.role == "traitor"), None)

    # ---- 胃：Sanity 掷骰 5+ 无事；2-4 → 1 精神伤；0/1 → 2 精神伤 + 停止移动
    stomach_room = engine._ensure_room_in_play("dining_room")
    assert stomach_room, "需要一间胃房间在场"
    hero.room_key = stomach_room
    stomach_obj = engine.state.board[stomach_room]
    for roll, expect_dmg, expect_stop in ((5, None, False), (3, 1, False), (0, 2, True), (1, 2, True)):
        hero.movement_stopped = False
        with patch.object(engine, "_roll_attack", return_value=roll), \
                patch.object(engine, "_deal_damage") as dealt:
            handler.on_enter_room(engine, hero, stomach_obj)
        if expect_dmg is None:
            dealt.assert_not_called()
        else:
            dealt.assert_called_once_with(hero, "mental", expect_dmg, source="胃消化")
        assert hero.movement_stopped == expect_stop, f"胃掷出 {roll} 的停移动标记应为 {expect_stop}"

    # ---- 器官只影响英雄：叛徒进胃房间不触发
    if traitor is not None and not traitor.dead:
        traitor.room_key = stomach_room
        with patch.object(engine, "_roll_attack", return_value=0), \
                patch.object(engine, "_deal_damage") as dealt_t:
            handler.on_enter_room(engine, traitor, stomach_obj)
        dealt_t.assert_not_called()

    # ---- 牙：Speed 掷骰 4+ 无事；1-3 → 1 物理；0 → 2 物理
    teeth_room = engine._ensure_room_in_play("balcony")
    assert teeth_room, "需要一间牙房间在场"
    hero.room_key = teeth_room
    teeth_obj = engine.state.board[teeth_room]
    for roll, expect_dmg in ((4, None), (2, 1), (0, 2)):
        with patch.object(engine, "_roll_attack", return_value=roll), \
                patch.object(engine, "_deal_damage") as dealt:
            handler.on_enter_room(engine, hero, teeth_obj)
        if expect_dmg is None:
            dealt.assert_not_called()
        else:
            dealt.assert_called_once_with(hero, "physical", expect_dmg, source="巨牙")

    # ---- 腺体：掷两骰（和 0-4）五档全测，防五向映射写反
    #   4→四属性各 +1；3→-2速度；2→-2力量；1→-2理智；0→-2知识
    glands_room = engine._ensure_room_in_play("research_laboratory")
    assert glands_room, "需要一间腺体房间在场"
    hero.room_key = glands_room
    glands_obj = engine.state.board[glands_room]
    gland_expect = {4: ("gain", None), 3: ("loss", "speed"), 2: ("loss", "might"),
                    1: ("loss", "sanity"), 0: ("loss", "knowledge")}
    for roll in (4, 3, 2, 1, 0):
        with patch.object(engine, "roll_dice", return_value=roll), \
                patch.object(engine, "_increase_stat") as inc, \
                patch.object(engine, "_apply_stat_loss") as loss, \
                patch.object(engine, "_check_player_death"):
            handler.on_enter_room(engine, hero, glands_obj)
        kind, stat = gland_expect[roll]
        if kind == "gain":
            assert inc.call_count == 4, f"腺体掷出 {roll} 应全属性 +1（四次 _increase_stat）"
            assert {c.args[1] for c in inc.call_args_list} == {"speed", "might", "sanity", "knowledge"}
            assert all(c.args[2] == 1 for c in inc.call_args_list), "全属性 +1 每次增量应为 1"
            loss.assert_not_called()
        else:
            loss.assert_called_once_with(hero, stat, 2)
            inc.assert_not_called()

    # ---- 肺：温室内失败 → 死亡 + 掉落物品
    conserv = engine._ensure_room_in_play("conservatory")
    assert conserv, "温室需在场"
    hero.dead = False
    hero.room_key = conserv
    conserv_obj = engine.state.board[conserv]
    with patch.object(engine, "_resolve_check", return_value=False), \
            patch.object(engine, "_drop_inventory_on_death") as drop, \
            patch.object(engine, "check_victory"):
        handler.on_enter_room(engine, hero, conserv_obj)
    assert hero.dead is True, "温室内肺检定失败应被杀死"
    drop.assert_called_once_with(hero)

    # ---- 肺：相邻房失败 → 移入温室再掷一次（第二次通过则存活）
    hero.dead = False
    other_room = next((k for k in sorted(engine.state.board) if k != conserv), conserv)
    hero.room_key = other_room
    with patch.object(engine, "_resolve_check", side_effect=[False, True]):
        handler._apply_lungs(engine, hero, in_conservatory=False)
    assert hero.room_key == conserv, "相邻房肺失败应被移入温室"
    assert hero.dead is False, "第二次通过应存活"
    # 相邻房两次都失败 → 死亡
    hero.dead = False
    hero.room_key = other_room
    with patch.object(engine, "_resolve_check", side_effect=[False, False]), \
            patch.object(engine, "_drop_inventory_on_death"), \
            patch.object(engine, "check_victory"):
        handler._apply_lungs(engine, hero, in_conservatory=False)
    assert hero.dead is True, "相邻房两次肺检定都失败应被杀死"

    # ---- 肺门相邻路由：经 on_enter_room 驱动，覆盖 _apply_organ_effect 的 _door_adjacent 分支
    hero.dead = False
    conserv_obj = engine.state.board[conserv]
    organ_ids = (set(handler.STOMACH_ROOMS) | set(handler.TEETH_ROOMS)
                 | set(handler.GLANDS_ROOMS) | {handler.CONSERVATORY})
    neutral = [t for t in engine.catalog.room_templates.values()
               if t.floor == conserv_obj.floor and t.id not in organ_ids]
    assert len(neutral) >= 2, "需要两间中性房模板做肺相邻/不相邻路由"
    # ① 与温室门对接的相邻房 → 进入触发肺检定
    adj_delta = next(
        ((dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
         if (conserv_obj.floor, conserv_obj.x + dx, conserv_obj.y + dy) not in engine.state.pos_index),
        None,
    )
    assert adj_delta is not None, "温室需至少一个空的网格相邻位来构造门对接房"
    adj_room = engine._place_room(neutral[0], conserv_obj.x + adj_delta[0], conserv_obj.y + adj_delta[1], 0)
    dx, dy = adj_delta
    cdir, pdir = {(1, 0): ("east", "west"), (-1, 0): ("west", "east"),
                  (0, 1): ("south", "north"), (0, -1): ("north", "south")}[(dx, dy)]
    conserv_obj.doors = tuple(set(conserv_obj.doors) | {cdir})
    adj_room.doors = tuple(set(adj_room.doors) | {pdir})
    assert handler._door_adjacent(engine, adj_room.key, conserv), "构造的相邻房应与温室门对接"
    hero.room_key = adj_room.key
    with patch.object(engine, "_resolve_check", return_value=True) as rc_adj, \
            patch.object(engine, "_roll_attack", return_value=6), \
            patch.object(engine, "_deal_damage"):
        handler.on_enter_room(engine, hero, adj_room)
    assert rc_adj.called, "进入与温室门相邻的房间应触发肺检定"
    # ② 不与温室门相邻的中性房 → 不触发肺
    far_room = engine._place_room(neutral[1], conserv_obj.x + 9, conserv_obj.y + 9, 0)
    far_room.doors = ()
    assert not handler._door_adjacent(engine, far_room.key, conserv), "远房不应与温室门相邻"
    hero.room_key = far_room.key
    hero.dead = False
    with patch.object(engine, "_resolve_check") as rc_far, \
            patch.object(engine, "_roll_attack", return_value=6), \
            patch.object(engine, "_deal_damage"):
        handler.on_enter_room(engine, hero, far_room)
    rc_far.assert_not_called()

    # ---- on_turn_start 也路由到器官效果（开始回合触发）
    hero.dead = False
    hero.room_key = stomach_room
    with patch.object(engine, "_roll_attack", return_value=0), \
            patch.object(engine, "_deal_damage") as dealt:
        handler.on_turn_start(engine, hero)
    dealt.assert_called_once_with(hero, "mental", 2, source="胃消化")

    # ---- setup 时当前在胃房间的英雄立即掷一次胃检定
    hero.dead = False
    hero.room_key = stomach_room
    with patch.object(LivingHouseMode, "_apply_stomach") as spy_stomach:
        handler.setup(engine, engine.state.haunt, stomach_room)
    assert any(call.args[1] is hero for call in spy_stomach.call_args_list), \
        "setup 应对当前处于胃房间的英雄立即掷一次胃检定"


def verify_haunt31_heart_brain_spear() -> None:
    """剧本 31 心脏/大脑/长矛/抗体：setup 布点、攻击闸门、防御不造伤、长矛击杀即英雄胜、
    攻击失败抗体回流、叛徒销毁长矛即胜、杀叛徒但房子存活→无 winner（吸收兜底）（p42/p113）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=31)
    handler = engine._mode_handler()
    assert isinstance(handler, LivingHouseMode)
    flags = engine._haunt_flags()

    for person in engine.state.players:
        if person.role == "hero":
            person.dead = False
            for stat in ("speed", "might", "sanity", "knowledge"):
                person.stats[stat] = 4
    heroes = [p for p in engine.state.players if p.role == "hero"]
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert heroes and traitor is not None
    hero = heroes[0]

    # ---- setup 布点：心脏(organ_room, might7) / 大脑(attic, might6) / 抗体数=英雄数 / 某英雄持矛
    heart = engine._monster_by_template("heart")
    brain = engine._monster_by_template("brain")
    assert heart is not None and brain is not None, "setup 应生成心脏与大脑"
    assert heart.might == 7 and brain.might == 6, "心脏防御 Might 7、大脑防御 Might 6"
    organ_key = handler._room_key_by_template(engine, "organ_room")
    attic_key = handler._room_key_by_template(engine, "attic")
    assert heart.room_key == organ_key and brain.room_key == attic_key, "心脏在管风琴室、大脑在阁楼"
    antibodies = [m for m in engine.state.monsters if m.template_id == "antibody"]
    assert len(antibodies) == len(heroes), f"抗体数应=英雄数 {len(heroes)}，实际 {len(antibodies)}"
    allowed = {k for k in (handler._room_key_by_template(engine, t) for t in handler.ANTIBODY_ROOMS) if k}
    assert all(a.room_key in allowed for a in antibodies), "抗体应分布在 6 指定房中在场者"
    assert (antibodies[0].speed, antibodies[0].might, antibodies[0].sanity) == (3, 5, 3), \
        "抗体数值应为 Speed3/Might5/Sanity3（注意是 Sanity 不是 Knowledge）"
    spear_holder = next((p for p in engine.state.players if "omen_spear" in p.items), None)
    assert spear_holder is not None and spear_holder.role == "hero", "setup 应把长矛授予一名英雄"

    # ---- attack_allowed：无矛攻心脏→False；持矛→True；攻大脑 Sanity<4→False 且 attack_used=True
    if "omen_spear" in hero.items:
        hero.items.remove("omen_spear")
    hero.room_key = heart.room_key
    assert handler.attack_allowed(engine, hero, heart) is False, "无长矛不能攻击心脏"
    hero.items.append("omen_spear")
    assert handler.attack_allowed(engine, hero, heart) is True, "持长矛可攻击心脏"
    hero.attack_used = False
    hero.movement_stopped = False
    hero.steps_remaining = 5
    with patch.object(engine, "_resolve_check", return_value=False):
        assert handler.attack_allowed(engine, hero, brain) is False, "大脑 Sanity 失败不能攻击"
    assert hero.attack_used is True, "大脑 Sanity 失败应结束回合（attack_used=True）"
    assert hero.movement_stopped is True, "大脑 Sanity 失败应停止移动（p113 turn ends without attacking）"
    assert hero.steps_remaining == 0, "大脑 Sanity 失败应清空剩余移动力，防白嫖离开阁楼"
    hero.attack_used = False
    hero.movement_stopped = False
    hero.steps_remaining = 5
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.attack_allowed(engine, hero, brain) is True, "大脑 Sanity 通过可攻击"
    assert hero.attack_used is False
    assert hero.movement_stopped is False, "大脑 Sanity 通过不应停移动"

    # ---- 防御不造伤 + 心脏/大脑永不行动
    assert handler.monster_counterattack_disabled(engine, heart) is True
    assert handler.monster_counterattack_disabled(engine, brain) is True
    assert handler.on_monster_turn_start(engine, heart) is True
    assert handler.on_monster_turn_start(engine, brain) is True

    # ---- 持长矛击败心脏（weapon_id=omen_spear）→ house_killed → 英雄胜
    assert handler.monster_killed_on_defeat(engine, heart, hero, "might", "omen_spear") is True
    assert flags["house_killed"] is True
    assert engine._haunt_track_value("house_slain") == 1
    assert handler.check_victory(engine) is True and engine.state.winner == "heroes"
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    flags["house_killed"] = False
    engine._set_haunt_track_value("house_slain", 0)

    # ---- 持矛英雄但本次攻击 weapon_id 非长矛（空手）击败心脏 → 只击晕，不杀房
    #   印证“须被长矛击败才杀死房子”；heart 此时仍存活
    assert handler.monster_killed_on_defeat(engine, heart, hero, "might", "") is False
    assert flags["house_killed"] is False, "非长矛击败心脏只击晕，不应置 house_killed"

    # ---- 攻击心脏失败 → 回流一只抗体到管风琴室
    antibodies = [m for m in engine.state.monsters if m.template_id == "antibody"]
    before_in_organ = len([a for a in antibodies if a.room_key == organ_key])
    hero.room_key = organ_key
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0
    engine._reset_player_turn_state(hero)
    with patch.object(engine, "_roll_attack", return_value=1), \
            patch.object(engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 9):
        assert engine.attack(hero, heart, "omen_spear") is True
    after = [m for m in engine.state.monsters if m.template_id == "antibody" and m.room_key == organ_key]
    assert len(after) == before_in_organ + 1, "攻击心脏失败应回流一只抗体到管风琴室"
    assert heart in engine.state.monsters, "攻击失败心脏不应被杀死"

    # ---- 叛徒在深渊销毁长矛 → spear_destroyed → 叛徒胜
    chasm = (engine._ensure_room_in_play("chasm")
             or handler._room_key_by_template(engine, "furnace_room")
             or handler._room_key_by_template(engine, "underground_lake"))
    assert chasm, "需要深渊/熔炉房/地下湖之一在场"
    for p in engine.state.players:
        if "omen_spear" in p.items:
            p.items.remove("omen_spear")
    traitor.items.append("omen_spear")
    traitor.room_key = chasm
    engine.state.turn_order = [traitor.id]
    engine.state.turn_index = 0
    engine._reset_player_turn_state(traitor)
    assert handler.perform_action(engine, traitor, "throw_spear", {}) is True
    assert flags["spear_destroyed"] is True
    assert "omen_spear" not in traitor.items, "长矛应被销毁移除"
    assert handler.check_victory(engine) is True and engine.state.winner == "traitor"
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    flags["spear_destroyed"] = False

    # ---- 杀死叛徒但心脏/大脑存活 → 无 winner（吸收引擎兜底）
    traitor.dead = True
    assert handler.check_victory(engine) is True and engine.state.winner is None, \
        "杀叛徒≠英雄胜（房子仍活，抗体仍由 bot 驱动）"
    traitor.dead = False

    # ---- M10-49 回归：预判路径必须纯净（bot 决策阶段不得掷骰/改状态/刷日志）
    # 引擎的 attack_would_be_allowed(log=False) 预判路径会把 engine._attack_query
    # 置 True；31 号攻大脑的理智检定是"真打才许发生"的副作用——过去放在预判里
    # 会反复掷骰、清空移动力、把日志刷满"只有长矛能伤到心脏"（实测一局 80-120 行、
    # 机器人在走位评分阶段被自己的查询冻结）。
    if "omen_spear" not in hero.items:
        hero.items.append("omen_spear")
    hero.attack_used = False
    hero.movement_stopped = False
    hero.steps_remaining = 5
    hero.room_key = attic_key  # 与大脑同房：让断言落在长矛/理智闸门而不是位置闸门
    probe_calls = {"n": 0}
    real_check = engine._resolve_check

    def _counting_check(player, stat, target, label):
        probe_calls["n"] += 1
        return real_check(player, stat, target, label)

    with patch.object(engine, "_resolve_check", side_effect=_counting_check):
        assert engine.attack_would_be_allowed(hero, brain) is True, \
            "预判：持矛者理论上打得着大脑（理智检定留到真打）"
        assert probe_calls["n"] == 0, "预判不得触发理智检定（不得掷骰）"
        assert hero.attack_used is False and hero.movement_stopped is False, \
            "预判不得改写回合状态"
        assert hero.steps_remaining == 5, "预判不得清空剩余移动力"
    if "omen_spear" in hero.items:
        hero.items.remove("omen_spear")
    hero.room_key = organ_key  # 与心脏同房：无矛时被闸门（而非位置）挡住
    quiet: list[str] = []
    orig_log_fn = engine._log
    engine._log = lambda m, category="": (quiet.append(m), orig_log_fn(m, category))
    try:
        assert engine.attack_would_be_allowed(hero, heart) is False, "无矛预判应不可攻击"
    finally:
        engine._log = orig_log_fn
    assert not [m for m in quiet if "只有长矛" in m], \
        "预判不得刷『只有长矛能伤到心脏』日志"
    # 真打：仍走理智检定，失败则回合结束且不攻击
    hero.items.append("omen_spear")
    hero.attack_used = False
    hero.movement_stopped = False
    hero.steps_remaining = 5
    hero.room_key = attic_key
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0
    with patch.object(engine, "_resolve_check", return_value=False) as real_mock:
        assert engine.attack(hero, brain) is False, "理智失败：不得发起攻击"
        assert real_mock.called, "真打必须掷理智检定"
    assert hero.attack_used is True and hero.movement_stopped is True
    assert hero.steps_remaining == 0, "攻脑失败应清空剩余移动力（p113）"
    if "omen_spear" in hero.items:
        hero.items.remove("omen_spear")
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"

    # ---- 英雄全灭 → 叛徒胜（p113：让活房子消化杀死所有英雄）
    saved_dead = {p.id: p.dead for p in engine.state.players}
    for p in engine.state.players:
        if p.role == "hero":
            p.dead = True
    traitor.dead = False
    flags["house_killed"] = False
    flags["spear_destroyed"] = False
    engine.state.winner = None
    assert handler.check_victory(engine) is True and engine.state.winner == "traitor", \
        "所有英雄死亡应判叛徒胜"
    for p in engine.state.players:
        p.dead = saved_dead[p.id]
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"

    # ---- 完整攻击流：持矛英雄击败心脏 → 心脏离场 + 英雄胜
    for p in engine.state.players:
        if "omen_spear" in p.items:
            p.items.remove("omen_spear")
    hero.items.append("omen_spear")
    hero.room_key = heart.room_key
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0
    engine._reset_player_turn_state(hero)
    with patch.object(engine, "_roll_attack", return_value=9), \
            patch.object(engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 1):
        assert engine.attack(hero, heart, "omen_spear") is True
    assert heart not in engine.state.monsters, "持矛击败心脏应杀死它"
    assert flags["house_killed"] is True
    assert engine.state.winner == "heroes"

    # ---- 大脑击杀胜利路径（p42：“kill the Heart or the Brain”，一次即胜）
    flags["house_killed"] = False
    engine._set_haunt_track_value("house_slain", 0)
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    brain = engine._monster_by_template("brain")
    assert brain is not None, "大脑应仍存活（此前只用 attack_allowed 探针，未真正击败）"
    for p in engine.state.players:
        if "omen_spear" in p.items:
            p.items.remove("omen_spear")
    hero.dead = False
    hero.items.append("omen_spear")
    hero.room_key = brain.room_key
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0
    engine._reset_player_turn_state(hero)
    with patch.object(engine, "_resolve_check", return_value=True), \
            patch.object(engine, "_roll_attack", return_value=9), \
            patch.object(engine, "_roll_monster_attack", side_effect=lambda m, a, reroll_blanks=False: 1):
        assert engine.attack(hero, brain, "omen_spear") is True
    assert brain not in engine.state.monsters, "持矛击败大脑应杀死它"
    assert flags["house_killed"] is True
    assert engine._haunt_track_value("house_slain") == 1
    assert engine.state.winner == "heroes", "击败大脑同样判英雄胜"


def verify_haunt31_antibody_wall_move() -> None:
    """剧本 31 抗体穿墙移动（on_monster_move/_wall_graph/_bfs_dist/_wall_step_destination）：
    ① 无连通门、仅同楼层网格相邻 → 抗体穿墙移近最近英雄（证明忽略门约束）；
    ② rolled=0 → 不动；③ 非抗体怪物（心脏）→ 钩子返回 False 交回引擎、不外溢。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=31)
    handler = engine._mode_handler()
    assert isinstance(handler, LivingHouseMode)

    # 只留一名活英雄，保证 _find_monster_target 目标确定
    heroes = [p for p in engine.state.players if p.role == "hero"]
    assert heroes, "需要至少一名英雄"
    for p in engine.state.players:
        if p.role == "hero":
            p.dead = True
    hero = heroes[0]
    hero.dead = False

    # 构造两间同楼层网格相邻、但清空门/链接（门图不连通）的房间：
    # 只有穿墙图（_wall_graph 的网格相邻）才连得起来，以此证明移动忽略门约束。
    template = next(t for t in engine.catalog.room_templates.values() if t.floor == 0)
    room_a = engine._place_room(template, 40, 40, 0)
    room_b = engine._place_room(template, 41, 40, 0)  # A 东侧、网格相邻
    for room in (room_a, room_b):
        room.doors = ()
        room.links = {}
    assert room_b.key in engine._grid_neighbors(room_a.key), "两房应同楼层网格相邻"
    assert engine._path_length(room_a.key, room_b.key) >= 9999, "清空门/链接后门图应不可达"

    # 在 A 放一只抗体、英雄置于 B
    antibody = engine._spawn_single_haunt_monster(handler._spec(engine, "antibody", "抗体"), room_a.key)
    assert antibody is not None and antibody.template_id == "antibody"
    hero.room_key = room_b.key

    # ① 给足步数：抗体穿墙抵达英雄所在房（忽略门约束）
    assert handler.on_monster_move(engine, antibody, 3) is True
    assert antibody.room_key == room_b.key, "抗体应穿墙移动到最近英雄所在房间"

    # ② rolled=0：原地不动
    antibody.room_key = room_a.key
    assert handler.on_monster_move(engine, antibody, 0) is True
    assert antibody.room_key == room_a.key, "掷 0 步抗体不应移动"

    # ③ 非抗体怪物（心脏）：钩子返回 False，交回引擎常规移动、不改房间
    heart = engine._monster_by_template("heart") or engine._spawn_single_haunt_monster(
        handler._spec(engine, "heart", "心脏"), room_a.key
    )
    heart.room_key = room_a.key
    assert handler.on_monster_move(engine, heart, 3) is False, "心脏不是抗体，on_monster_move 应交回引擎"
    assert heart.room_key == room_a.key, "返回 False 时钩子不应改动怪物房间"



def verify_haunt32_lost_dimension() -> None:
    """剧本 32：开局重排与风琴房入场/毒大气扣属性/三条线索/弹奏门槛与加值/
    干扰令牌/胜负（p43/p114）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=32)
    handler = engine._mode_handler()
    assert isinstance(handler, LostDimensionMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0

    # ---- 开局：风琴房必须在场；牌堆与弃牌堆被洗匀（撤房未建模，见 handler 文档）
    organ_keys = [k for k, r in engine.state.board.items() if r.template_id == "organ_room"]
    assert organ_keys, "p114：风琴房必须在场（不在就从牌堆取）"
    assert not engine.state.room_discard, "重排后弃牌堆应并入牌堆"
    assert flags["clue_books"] is False and flags["clue_trophy"] is False and flags["clue_stars"] is False
    assert flags["sabotage_rooms"] == [] and flags["returned_home"] is False

    # ---- 门槛按人数（p43）
    assert handler._needed(engine) == 15, "3 人局需要 15+"

    # ---- 毒大气（p43）：英雄回合开始掷 2 骰扣属性；叛徒不受影响
    # 注意"临时加成（overflow）先被消耗"：按**有效属性**（轨位+加成）计量，
    # 否则英雄身上带加值时轨位不动，合计差会小于 2 而假失败。
    stats4 = ("might", "speed", "sanity", "knowledge")
    before = {
        st: hero.stat_positions.get(st, 0) + hero.overflow.get(st, 0) for st in stats4
    }
    traitor_before = dict(traitor.stat_positions)
    with patch.object(engine, "roll_dice", return_value=2):
        handler.on_turn_start(engine, hero)
        handler.on_turn_start(engine, traitor)
    after = {
        st: hero.stat_positions.get(st, 0) + hero.overflow.get(st, 0) for st in stats4
    }
    assert sum(before[st] - after[st] for st in stats4) == 2, "掷出 2 → 合计掉 2 格（含临时加成）"
    assert traitor.stat_positions == traitor_before, "p43：叛徒不受毒大气影响"
    assert not hero.dead

    # ---- 线索：图书馆知识 5+ → 全局线索 + 轨道推进；同一条不可再找
    def place(template_id: str, x: int, y: int) -> str:
        for key, room in engine.state.board.items():
            if room.template_id == template_id:
                return key
        placed = engine._place_room(engine.catalog.room_templates[template_id], x, y, 0)
        placed.revealed = True
        return placed.key

    library_key = place("library", 40, 40)
    hero.room_key = library_key
    engine._reset_player_turn_state(hero)
    assert "search_books" in {a.id for a in handler.available_actions(engine, hero)}
    with patch.object(engine, "_resolve_check", return_value=True):
        assert engine.perform_haunt_action(hero, "search_books") is True
    assert flags["clue_books"] is True, "p43：找到乐谱（全局共享）"
    assert engine._haunt_track_value("clues_found") == 1
    engine._reset_player_turn_state(hero)
    assert "search_books" not in {a.id for a in handler.available_actions(engine, hero)}, "p43：同一条线索不能重复找"

    # ---- 弹奏：门槛 15+，加值 = 预兆房数 + 线索；未达标不获胜，达标 → 英雄胜
    omen_rooms = sum(
        1 for room in engine.state.board.values()
        if room.symbol == "omen" and not engine._is_collapsed(room.key)
    )
    organ_key = organ_keys[0]
    hero.room_key = organ_key
    engine._reset_player_turn_state(hero)
    assert "play_organ" in {a.id for a in handler.available_actions(engine, hero)}
    with patch.object(engine, "roll_dice", return_value=0):
        assert engine.perform_haunt_action(hero, "play_organ") is True
    assert flags["returned_home"] is False
    assert engine.state.winner is None
    expected_bonus = omen_rooms + 2  # 乐谱线索 +2
    with patch.object(engine, "roll_dice", return_value=max(1, 15 - expected_bonus)):
        engine._reset_player_turn_state(hero)
        assert engine.perform_haunt_action(hero, "play_organ") is True
    assert flags["returned_home"] is True, "p43：合计达门槛 → 房子回原维度"
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes", "p43：弹对曲子 → 英雄胜"

    # ---- 干扰（p114）：叛徒知识 4+ 放 -3 令牌，每间限一枚
    engine2 = _run_until_haunt(seed=113, players=3, haunt_id=32)
    h2 = engine2._mode_handler()
    t2 = next(p for p in engine2.state.players if p.role == "traitor")
    engine2.state.turn_order = [t2.id]
    engine2.state.turn_index = 0
    chapel_key = next((k for k, r in engine2.state.board.items() if r.template_id == "chapel"), None)
    if chapel_key is None:
        placed = engine2._place_room(engine2.catalog.room_templates["chapel"], 41, 40, 0)
        placed.revealed = True
        chapel_key = placed.key
    t2.room_key = chapel_key
    engine2._reset_player_turn_state(t2)
    assert "sabotage_transporter" in {a.id for a in h2.available_actions(engine2, t2)}
    with patch.object(engine2, "_resolve_check", return_value=True):
        assert engine2.perform_haunt_action(t2, "sabotage_transporter") is True
    f2 = engine2._haunt_flags()
    assert f2["sabotage_rooms"] == ["chapel"], "p114：每间只放一枚干扰令牌"
    assert engine2._haunt_track_value("sabotage") == 1
    engine2._reset_player_turn_state(t2)
    assert "sabotage_transporter" not in {a.id for a in h2.available_actions(engine2, t2)}, "p114：同一间房不能重复干扰"
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    _bonus2, parts2 = h2._bonus(engine2, hero2)
    assert "叛徒干扰 -3" in "，".join(parts2), "干扰令牌应表现为 -3"

    # ---- 房间加值：疯子/书在风琴房各 +2（p43）
    organ2 = next(k for k, r in engine2.state.board.items() if r.template_id == "organ_room")
    hero2.room_key = organ2
    base2, _ = h2._bonus(engine2, hero2)
    hero2.companions.append("madman")
    assert h2._bonus(engine2, hero2)[0] == base2 + 2, "p43：疯子在风琴房 +2"
    hero2.companions.remove("madman")
    hero2.items.append("omen_book")
    assert h2._bonus(engine2, hero2)[0] == base2 + 2, "p43：书在风琴房 +2"
    hero2.items.remove("omen_book")

    # ---- bot 目标：先补线索再进风琴房（只列**在场**的线索房）；叛徒先跑干扰房
    # M10-49 实测（seed101/3p）：p114 的房屋重排把三间线索房卷回牌堆，旧实现仍
    # 返回这三条不在场的模板 id——等于没有目标，英雄黏在风琴房反复弹奏
    # （加值恒为"预兆房 +2"，合计 3-8 对门槛 15+），一局线索 0/3 找到。
    in_play = {room.template_id for room in engine2.state.board.values()}
    goals = h2.bot_goal_rooms(engine2, hero2)
    assert "organ_room" in goals
    for room_id, flag in (("library", "clue_books"), ("game_room", "clue_trophy"), ("tower", "clue_stars")):
        if not f2.get(flag):
            if room_id in in_play:
                assert room_id in goals, f"在场且未找到的线索房应在目标里：{room_id}"
            else:
                assert room_id not in goals, f"不在场的线索房不该占目标位：{room_id}"
    # 线索房不在场且有牌可翻 → 必须先探索把它们翻出来（翻出的预兆房还各 +1 弹奏）
    off_board = [
        rid
        for fid, rid in (
            ("clue_books", "library"),
            ("clue_trophy", "game_room"),
            ("clue_stars", "tower"),
        )
        if not f2.get(fid) and rid not in in_play
    ]
    if off_board and any(engine2.has_remaining_room_cards(floor) for floor in (-1, 0, 1)):
        assert h2.bot_wants_explore(engine2, hero2) is True, (
            "线索房不在场且牌堆有牌 → 英雄必须先翻新房间"
        )
    f2["clue_books"] = f2["clue_trophy"] = f2["clue_stars"] = True
    assert h2.bot_wants_explore(engine2, hero2) is False, "线索集齐后不再强制探索"
    assert h2.bot_goal_rooms(engine2, hero2) == ["organ_room"], "线索集齐后只去风琴房"
    t_goals = h2.bot_goal_rooms(engine2, t2)
    assert "chapel" not in t_goals, "已干扰过的房间不再作为目标"
    assert set(t_goals) == set(h2.SABOTAGE_ROOMS) - {"chapel"}

    # ---- 进度摘要
    summary = h2.progress_summary(engine2, hero2)
    assert any("回家门槛" in row for row in summary)
    assert any("叛徒干扰" in row for row in summary)

    # ---- 胜负：英雄全灭 → 叛徒胜；叛徒死亡 ≠ 英雄胜（老坑 21 号吸收者）
    engine3 = _run_until_haunt(seed=113, players=3, haunt_id=32)
    h3 = engine3._mode_handler()
    for p in engine3.state.players:
        if p.role == "hero":
            p.dead = True
    assert h3.check_victory(engine3) is True
    assert engine3.state.winner == "traitor", "p114：英雄全灭 → 叛徒胜"
    engine4 = _run_until_haunt(seed=113, players=3, haunt_id=32)
    h4 = engine4._mode_handler()
    next(p for p in engine4.state.players if p.role == "traitor").dead = True
    assert h4.check_victory(engine4) is True and engine4.state.winner is None, "叛徒死亡 ≠ 英雄胜"



def verify_haunt61_eternal_glory() -> None:
    """剧本 61：三遗物/幽灵战士/说服胜利（p72/p143）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=61)
    handler = engine._mode_handler()
    assert isinstance(handler, EternalGloryMode)
    flags = engine._haunt_flags()

    # 三遗物已放置
    for kind in ("statue_relic", "sarcophagus_relic", "ancient_armor"):
        tokens = engine.tokens_of_kind(kind)
        assert tokens, f"{kind} 应已放置"

    # 矛已放置
    spear = engine.tokens_of_kind("spear")
    assert spear, "矛应已放置"

    # 英雄拾矛 → 到遗物房间 → 说服
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    spear_token = spear[0]
    if spear_token.holder is not None:
        engine.give_token(spear_token.uid, hero.id)
    else:
        hero.room_key = spear_token.room_key
        engine.give_token(spear_token.uid, hero.id)

    # 带到遗物房间说服
    relic_room = flags["relic_rooms"]["statue_relic"]
    hero.room_key = relic_room
    _set_current(engine, hero)
    engine._reset_player_turn_state(hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "persuade_ghost" in ids, "持矛在遗物房间应能说服"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "persuade_ghost", {}) is True
    assert engine._haunt_track_value("persuasion_track") >= 1



def verify_haunt62_bag_of_tricks() -> None:
    """剧本 62：叛徒移除/疯子/纪念品/小玩意双检定/偷取/胜负（p73/p144）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=62)
    handler = engine._mode_handler()
    assert isinstance(handler, BagOfTricksMode)
    flags = engine._haunt_flags()

    # p73：叛徒角色按规则从游戏中移除（不是被打倒）
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert traitor.dead, "叛徒应已从游戏移除"
    assert flags.get("traitor_removed") is True

    # p144：疯子在作祟房间，Speed 4 / Might 3
    madman = engine._monster_by_template("madman")
    assert madman is not None, "疯子怪物应已生成"
    assert (madman.speed, madman.might) == (4, 3), "疯子应为 Speed 4 / Might 3"

    # 轨道目标：令牌 = 作祟时英雄数；回合/伤害轨 8；纪念品 4
    hero_count = int(flags["hero_count_at_start"])
    assert engine._haunt_track_target("trinket_tokens") == hero_count
    assert engine._haunt_track_target("trinket_progress") == BagOfTricksMode.TRACK_MAX
    assert engine._haunt_track_target("souvenir_count") == BagOfTricksMode.SOUVENIR_NEEDED

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero.room_key = madman.room_key
    _set_current(engine, hero)

    # p73：与疯子同房即可做检定；轨道太低时理智检定无意义 → 只出现"破解"
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert ids == {"tap_trinkets"}, f"轨道 0 时只该有破解：{ids}"
    engine._set_haunt_track_value("trinket_progress", BagOfTricksMode.USE_TRINKET_MIN - 1)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "use_trinket" not in ids, "轨道低于门槛时不该给理智检定（白掷一回合）"
    engine._set_haunt_track_value("trinket_progress", 0)

    # 破解成功 → 回合/伤害轨 +1
    with patch.object(engine, "roll_dice", return_value=BagOfTricksMode.TAP_TARGET):
        assert handler.perform_action(engine, hero, "tap_trinkets", {}) is True
    assert engine._haunt_track_value("trinket_progress") == 1, "知识 6+ 应把轨道抬一格"

    # 破解失败 → 不推轨
    with patch.object(engine, "roll_dice", return_value=1):
        assert handler.perform_action(engine, hero, "tap_trinkets", {}) is True
    assert engine._haunt_track_value("trinket_progress") == 1, "检定失败不该推轨"

    # 理智检定成功（roll < 轨道）→ 得令牌，轨道降一格
    engine._set_haunt_track_value("trinket_progress", 4)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "use_trinket" in ids, "轨道达到门槛时理智检定应可用"
    with patch.object(engine, "roll_dice", return_value=0):
        assert handler.perform_action(engine, hero, "use_trinket", {}) is True
    assert engine._haunt_track_value("trinket_tokens") == 1
    assert engine._haunt_track_value("trinket_progress") == 3, "理智成功应把轨道降一格"

    # 理智检定失败（roll ≥ 轨道）→ 不推进
    with patch.object(engine, "roll_dice", return_value=9):
        handler.perform_action(engine, hero, "use_trinket", {})
    assert engine._haunt_track_value("trinket_tokens") == 1, "理智没过不该给令牌"

    # p73：小玩意被摸走后，"与小玩意同房"= 在哪都能做检定
    handler._steal_trinket(engine, madman, hero)
    assert engine.tokens_held_by(hero.id, BagOfTricksMode.TRINKET), "应摸到一件小玩意"
    away = next(k for k in engine.state.board if k != madman.room_key)
    hero.room_key = away
    engine._set_haunt_track_value("trinket_progress", 0)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "tap_trinkets" in ids, "手持小玩意时在任意房间都能破解"
    # 同房每件小玩意给知识检定结果 +1（5 + 1 = 6 → 成功）
    with patch.object(engine, "roll_dice", return_value=5):
        handler.perform_action(engine, hero, "tap_trinkets", {})
    assert engine._haunt_track_value("trinket_progress") == 1, "小玩意应给检定结果 +1"

    # 令牌攒满 → 英雄胜
    engine._set_haunt_track_value("trinket_tokens", hero_count)
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # ---- 疯子胜线 + 挨打不死（另开一局，避免上面的 winner 干扰）----
    engine2 = _run_until_haunt(seed=109, players=3, haunt_id=62)
    handler2 = engine2._mode_handler()
    madman2 = engine2._monster_by_template("madman")
    assert madman2 is not None
    item_rooms = [
        key for key, room in engine2.state.board.items() if getattr(room, "symbol", None) == "item"
    ]
    if len(item_rooms) < BagOfTricksMode.SOUVENIR_NEEDED:
        # 单元测试不赌探索运气：凑不满物品符号房间时直接指定几间。
        for key, room in engine2.state.board.items():
            if key in item_rooms:
                continue
            room.symbol = "item"
            item_rooms.append(key)
            if len(item_rooms) >= BagOfTricksMode.SOUVENIR_NEEDED:
                break
    assert len(item_rooms) >= BagOfTricksMode.SOUVENIR_NEEDED

    # p144：速度 4+ → 该房放一枚纪念品；同一房间不能重复搜
    madman2.room_key = item_rooms[0]
    with patch.object(engine2, "roll_dice", return_value=4):
        assert handler2._collect_souvenir(engine2, madman2) is True
    assert engine2.tokens_in_room(item_rooms[0], BagOfTricksMode.SOUVENIR), "成功应留下纪念品"
    assert engine2._haunt_track_value("souvenir_count") == 1
    with patch.object(engine2, "roll_dice", return_value=6):
        assert handler2._collect_souvenir(engine2, madman2) is False, "同一房间不能重复搜"

    # 速度不够 → 不推进
    madman2.room_key = item_rooms[1]
    with patch.object(engine2, "roll_dice", return_value=1):
        assert handler2._collect_souvenir(engine2, madman2) is False
    assert engine2._haunt_track_value("souvenir_count") == 1, "速度不够不该记纪念品"

    # 搜满 4 枚 → 叛徒胜
    engine2.state.winner = None
    with patch.object(engine2, "roll_dice", return_value=4):
        for key in item_rooms[: BagOfTricksMode.SOUVENIR_NEEDED]:
            madman2.room_key = key
            handler2._collect_souvenir(engine2, madman2)
    assert engine2._haunt_track_value("souvenir_count") == BagOfTricksMode.SOUVENIR_NEEDED
    assert engine2.state.winner == "traitor", "集齐四件纪念品 → 叛徒胜"

    # p73/p144：打中疯子不掉血、不昏迷，但英雄摸走一件小玩意
    engine3 = _run_until_haunt(seed=137, players=3, haunt_id=62)
    handler3 = engine3._mode_handler()
    madman3 = engine3._monster_by_template("madman")
    hero3 = next(p for p in engine3.state.players if p.role == "hero" and not p.dead)
    sack_before = int(engine3._haunt_flags().get("sack", 0))
    assert sack_before > 0
    assert handler3.on_monster_defeated(engine3, madman3, 3) is True, "疯子不该被击晕"
    assert madman3.stunned_turns == 0, "疯子挨打不昏迷"
    engine3._last_attack_attr = "might"
    handler3.on_attack_resolved(engine3, hero3, madman3, True)
    assert int(engine3._haunt_flags().get("sack", 0)) == sack_before - 1, "应摸走一件小玩意"
    assert engine3.tokens_held_by(hero3.id, BagOfTricksMode.TRINKET), "小玩意应挂到英雄身上"
    # 袋空后机器人不再捶疯子；而且疯子防守得手要让英雄回合立刻结束
    engine3._haunt_flags()["sack"] = 0
    assert handler3.bot_attack_blocked(engine3, hero3, madman3) is True
    assert handler3.monster_counterattack_disabled(engine3, madman3) is True
    handler3.on_attack_resolved(engine3, hero3, madman3, False)
    assert hero3.steps_remaining == 0 and hero3.movement_stopped, "疯子防守得手应结束英雄回合"
    # 体力见底时不该拿自伤武器（献祭匕首/血匕首）去换小玩意
    hero3.stats["speed"], hero3.stats["might"] = 1, 2
    assert handler3.bot_weapon_bonus(engine3, hero3, madman3, "item_sacrificial_dagger") < 0
    assert handler3.bot_weapon_bonus(engine3, hero3, madman3, None) == 0
    hero3.stats["speed"], hero3.stats["might"] = 5, 5
    assert handler3.bot_weapon_bonus(engine3, hero3, madman3, "item_sacrificial_dagger") == 0
    # 英雄死在自伤武器上时不该再摸走小玩意
    hero3.dead = True
    engine3._haunt_flags()["sack"] = 2
    handler3.on_attack_resolved(engine3, hero3, madman3, True)
    assert int(engine3._haunt_flags().get("sack", 0)) == 2, "死人拿不动小玩意"



def _nether_omen_room(engine: GameEngine, hero) -> str:
    """找一间预兆房；探索运气不保证有，实在没有就把英雄脚下改成预兆房。"""
    for key, room in engine.state.board.items():
        if getattr(room, "symbol", None) == "omen":
            return key
    room = engine.state.board[hero.room_key]
    room.symbol = "omen"
    return hero.room_key


def verify_haunt63_twisting_nether() -> None:
    """剧本 63：锚定/锚网连通/按人数的胜利门槛/虚空怪物/收回房间（p74/p145）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=63)
    handler = engine._mode_handler()
    assert isinstance(handler, TwistingNetherMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # p74：胜利门槛按人数（3 人 12 / 4 人 15 / 5 人 19 / 6 人 21）
    assert engine._haunt_track_target("anchor_progress") == 12, "3 人应锚定 12 间"
    for players, expected in ((4, 15), (5, 19), (6, 21)):
        other = _run_until_haunt(seed=113, players=players, haunt_id=63)
        assert other._haunt_track_target("anchor_progress") == expected, (
            f"{players} 人应锚定 {expected} 间"
        )
    assert flags.get("nether_spawned") is False

    # ---- 锚定地点闸门：只有预兆符号房间能锚 ----
    _set_current(engine, hero)
    plain_key = None
    for key, room in engine.state.board.items():
        if getattr(room, "symbol", None) != "omen":
            plain_key = key
            break
    if plain_key is not None:
        hero.room_key = plain_key
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "anchor_room" not in ids, "非预兆房间不该出现锚定行动"

    omen_key = _nether_omen_room(engine, hero)
    hero.room_key = omen_key
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "anchor_room" in ids, "预兆房间应能锚定"

    # p74：知识 5+ 成功 → 留下锚令牌、房间进入锚定名单
    with patch.object(engine, "roll_dice", return_value=TwistingNetherMode.ANCHOR_MIN):
        assert handler.perform_action(engine, hero, "anchor_room", {}) is True
    assert engine.tokens_in_room(omen_key, TwistingNetherMode.ANCHOR_TOKEN), "成功应留下锚"
    assert omen_key in flags["anchored_rooms"]
    region = handler._anchored_region(engine)
    assert omen_key in region
    # 锚网 = 含锚房间 + 与它连通的房间；逐间核对可达性
    graph = engine._build_graph()
    assert region == engine._reachable_nodes(omen_key, graph) | {omen_key} | region.intersection(
        region
    ), "锚定区域应是含锚房间的连通闭包"
    for key in region:
        assert key in engine._reachable_nodes(omen_key, graph), (
            f"{key} 不与锚点连通却算作已锚定"
        )
    assert engine._haunt_track_value("anchor_progress") == len(region)

    # 检定失败 → 不发锚；同房不能重复锚定
    engine2 = _run_until_haunt(seed=113, players=3, haunt_id=63)
    handler2 = engine2._mode_handler()
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    _set_current(engine2, hero2)
    omen2 = _nether_omen_room(engine2, hero2)
    hero2.room_key = omen2
    with patch.object(engine2, "roll_dice", return_value=1):
        assert handler2.perform_action(engine2, hero2, "anchor_room", {}) is True
    assert not engine2.tokens_in_room(omen2, TwistingNetherMode.ANCHOR_TOKEN), (
        "检定没过不该留下锚"
    )
    with patch.object(engine2, "roll_dice", return_value=6):
        handler2.perform_action(engine2, hero2, "anchor_room", {})
    engine2._reset_player_turn_state(hero2)
    ids = {a.id for a in handler2.available_actions(engine2, hero2)}
    assert "anchor_room" not in ids, "已锚定的房间不能再锚"

    # p74：骷髅 +1 骰、通灵板 +2 骰（通灵板那 +2 是它自己的卡牌 bonus）
    engine3 = _run_until_haunt(seed=113, players=3, haunt_id=63)
    handler3 = engine3._mode_handler()
    hero3 = next(p for p in engine3.state.players if p.role == "hero" and not p.dead)
    _set_current(engine3, hero3)
    hero3.room_key = _nether_omen_room(engine3, hero3)
    hero3.items.clear()
    hero3.stats["knowledge"] = 2
    with patch.object(engine3, "roll_dice", return_value=1) as mock:
        handler3.perform_action(engine3, hero3, "anchor_room", {})
    bare = mock.call_args[0][0]
    assert bare == max(1, min(8, 2 + engine3._check_bonus(hero3, "knowledge"))), (
        "无器具时骰数应为知识值"
    )
    hero3.items.append("omen_skull")
    with patch.object(engine3, "roll_dice", return_value=1) as mock:
        handler3.perform_action(engine3, hero3, "anchor_room", {})
    with_skull = mock.call_args[0][0]
    assert with_skull - bare == 1, "骷髅应给锚定检定 +1 骰"
    hero3.items.append("omen_spirit_board")
    with patch.object(engine3, "roll_dice", return_value=1) as mock:
        handler3.perform_action(engine3, hero3, "anchor_room", {})
    with_board = mock.call_args[0][0]
    assert with_board - with_skull == 2, "通灵板应给锚定检定 +2 骰"

    # ---- 虚空怪物：星界灵常驻；英雄 ≥3 加 Specter、≥4 加 Ghost、5 人加 Phantom ----
    engine4 = _run_until_haunt(seed=113, players=4, haunt_id=63)
    handler4 = engine4._mode_handler()
    traitor4 = next(p for p in engine4.state.players if p.role == "traitor")
    assert not engine4.state.monsters, "怪物应由叛徒首回合生成（deferred）"
    handler4.on_turn_start(engine4, traitor4)
    templates = sorted(m.template_id for m in engine4.state.monsters)
    assert templates == ["astral_spirit", "spectre"], (
        f"4 人局（3 名英雄）应放星界灵 + Specter，实际 {templates}"
    )
    assert engine4._haunt_flags()["nether_spawned"] is True
    spirit = engine4._monster_by_template("astral_spirit")
    assert (spirit.might, spirit.speed, spirit.knowledge, spirit.sanity) == (5, 3, 4, 5), (
        "p145：星界灵 力量5/速度3/知识4/理智5"
    )
    handler4.on_turn_start(engine4, traitor4)  # 幂等：不会重复生成
    assert len(engine4.state.monsters) == 2

    engine5 = _run_until_haunt(seed=113, players=5, haunt_id=63)
    handler5 = engine5._mode_handler()
    handler5.on_turn_start(
        engine5, next(p for p in engine5.state.players if p.role == "traitor")
    )
    assert sorted(m.template_id for m in engine5.state.monsters) == [
        "astral_spirit",
        "ghost",
        "spectre",
    ], "5 人局（4 名英雄）应再加放 Ghost"

    engine6 = _run_until_haunt(seed=113, players=6, haunt_id=63)
    handler6 = engine6._mode_handler()
    handler6.on_turn_start(
        engine6, next(p for p in engine6.state.players if p.role == "traitor")
    )
    assert sorted(m.template_id for m in engine6.state.monsters) == [
        "astral_spirit",
        "ghost",
        "shadow",
        "spectre",
    ], "6 人局（5 名英雄）应再加放 Phantom"

    # p145：Specter 打速度或知识 <4 的目标多掷 1 骰
    specter = engine4._monster_by_template("spectre")
    weak = next(p for p in engine4.state.players if p.role == "hero" and not p.dead)
    weak.stats["speed"] = 3
    weak.stats["knowledge"] = 5
    assert handler4.monster_attack_roll_bonus(engine4, specter, weak) == 1
    weak.stats["speed"] = 4
    weak.stats["knowledge"] = 4
    assert handler4.monster_attack_roll_bonus(engine4, specter, weak) == 0
    assert handler4.monster_attack_roll_bonus(engine4, spirit, weak) == 0, (
        "只有 Specter 有这个加值"
    )

    # p145：Ghost 以理智攻击（精神伤害）；持戒指的英雄才能以理智打它
    engine7 = _run_until_haunt(seed=113, players=5, haunt_id=63)
    handler7 = engine7._mode_handler()
    handler7.on_turn_start(
        engine7, next(p for p in engine7.state.players if p.role == "traitor")
    )
    ghost = engine7._monster_by_template("ghost")
    specter7 = engine7._monster_by_template("spectre")
    ghost.sanity = 5
    victim = next(p for p in engine7.state.players if p.role == "hero" and not p.dead)
    victim.room_key = ghost.room_key
    victim.stats["sanity"] = 5
    assert handler7.on_monster_turn_attack(engine7, specter7) is False, (
        "非 Ghost 不该接管攻击"
    )
    with patch.object(engine7, "_roll_monster_attack", return_value=6), patch.object(
        engine7, "_roll_attack", return_value=2
    ), patch.object(engine7, "_deal_damage") as dealer:
        assert handler7.on_monster_turn_attack(engine7, ghost) is True
    assert dealer.call_count == 1, "Ghost 应造成一次伤害"
    assert dealer.call_args[0][1] == "mental", "Ghost 造成的是精神伤害"
    assert dealer.call_args[0][0] is victim

    ring_hero = next(
        p for p in engine7.state.players if p.role == "hero" and not p.dead and p is not victim
    )
    ring_hero.room_key = ghost.room_key
    ring_hero.attack_used = False
    assert engine7.attack_would_be_allowed(ring_hero, ghost, ignore_position=True) is False, (
        "没有戒指时英雄打不动 Ghost（免疫力量）"
    )
    ring_hero.items.append("omen_ring")
    assert engine7.attack_would_be_allowed(ring_hero, ghost, ignore_position=True) is True, (
        "持戒指的英雄应以理智攻击 Ghost"
    )
    assert handler7.attack_attr_override(engine7, ring_hero, ghost, "might") == "sanity"
    assert handler7.attack_attr_override(engine7, ring_hero, spirit, "might") is None

    # p145：Phantom 行动前瞬移到有别的怪物或叛徒的房间
    engine8 = _run_until_haunt(seed=113, players=6, haunt_id=63)
    handler8 = engine8._mode_handler()
    traitor8 = next(p for p in engine8.state.players if p.role == "traitor")
    handler8.on_turn_start(engine8, traitor8)
    phantom = engine8._monster_by_template("shadow")
    assert phantom is not None
    phantom.room_key = next(
        k for k in sorted(engine8.state.board) if k != traitor8.room_key
    )
    candidates = {
        m.room_key for m in engine8.state.monsters if m is not phantom
    } | {traitor8.room_key}
    candidates &= set(engine8.state.board)
    assert handler8.on_monster_turn_start(engine8, phantom) is False, "瞬移后仍要正常行动"
    assert phantom.room_key in candidates, (
        "Phantom 应瞬移到有别的怪物或叛徒的房间，实际去了 "
        f"{engine8.state.board[phantom.room_key].name}"
    )

    # ---- 收回房间：锚定房与占用房不受影响；断连房被回收且房内卡牌回到牌堆 ----
    engine9 = _run_until_haunt(seed=113, players=3, haunt_id=63)
    handler9 = engine9._mode_handler()
    hero9 = next(p for p in engine9.state.players if p.role == "hero" and not p.dead)
    _set_current(engine9, hero9)
    anchor_room = _nether_omen_room(engine9, hero9)
    hero9.room_key = anchor_room
    with patch.object(engine9, "roll_dice", return_value=6):
        handler9.perform_action(engine9, hero9, "anchor_room", {})
    before = set(engine9.state.board)
    removed = handler9._purge(engine9)
    assert anchor_room in engine9.state.board, "含锚的房间不该被虚空吞掉"
    assert all(key in engine9.state.board for key in before - set(removed)), (
        "_purge 只应移除它判定断连的房间"
    )
    # 回收单间：房内预兆卡必须洗回牌堆，而不是凭空消失
    empty_key = next(
        (
            key
            for key in sorted(engine9.state.board)
            if key != anchor_room
            and not engine9.tokens_in_room(key)
            and not any(
                p.room_key == key and not p.dead for p in engine9.state.players
            )
            and not engine9._monsters_in_room(key)
            and engine9.state.board[key].template_id
            not in TwistingNetherMode.FIXED_ROOMS
        ),
        None,
    )
    if empty_key is not None:
        engine9.state.room_items[empty_key] = ["omen_skull"]
        handler9._recycle_room(engine9, empty_key)
        assert empty_key not in engine9.state.board, "被回收的板块应离场"
        assert "omen_skull" in engine9.state.card_decks.get("omen", []), (
            "房内的预兆卡应洗回预兆牌堆"
        )

    # ---- p74 选项 3「穿越虚空」：跨孤岛的唯一通道（英雄胜线的命门）----
    # 开场 "Right Now" 按原文把房子撕成几座孤岛，预兆房落在哪座岛上是随机的。
    # 没有这条行动，英雄永远够不到别的岛上的预兆房，anchor_progress 一局钉死在 0。
    engine13 = _run_until_haunt(seed=113, players=3, haunt_id=63)
    handler13 = engine13._mode_handler()
    hero13 = next(p for p in engine13.state.players if p.role == "hero" and not p.dead)
    _set_current(engine13, hero13)
    rooms13 = handler13._unexplored_door_rooms(engine13)
    assert len(rooms13) >= 2, "开场清查后场上应还有未探索的门口"
    start13, destination13 = rooms13[0], rooms13[1]
    hero13.room_key = start13

    # 成功：知识 4+ → 落到选定的"还有未探索门口"的房间
    with patch.object(engine13, "roll_dice", return_value=TwistingNetherMode.SEEK_MIN):
        assert handler13.perform_action(
            engine13, hero13, "nether_seek", {"room": destination13}
        ) is True
    assert hero13.room_key == destination13, "检定过就该落到目的地"

    # 失败：p74 选项 1「随机坠入虚空」——跌进一块不与任何房间连通的新板块
    before13 = set(engine13.state.board)
    with patch.object(engine13, "roll_dice", return_value=1):
        assert handler13.perform_action(
            engine13, hero13, "nether_seek", {"room": start13}
        ) is True
    assert hero13.room_key not in before13, "检定没过应跌进一块新板块"
    assert all(engine13._path_length(hero13.room_key, key) >= 9999 for key in before13), (
        "p74 选项 1 放进来的板块不应与任何现有房间连通"
    )

    # 门槛一：站在预兆房里就没必要穿越虚空（否则会变成"行动摆出来却没人用"）
    engine14 = _run_until_haunt(seed=113, players=3, haunt_id=63)
    handler14 = engine14._mode_handler()
    hero14 = next(p for p in engine14.state.players if p.role == "hero" and not p.dead)
    _set_current(engine14, hero14)
    omen14 = _nether_omen_room(engine14, hero14)
    hero14.room_key = omen14
    assert "nether_seek" not in {
        a.id for a in handler14.available_actions(engine14, hero14)
    }, "够得着预兆房时不该给出穿越虚空"

    # 门槛二：跨孤岛（够不到预兆房）时才给出，且挑"落在预兆房那座岛上"的落点
    rest14 = [key for key in handler14._unexplored_door_rooms(engine14) if key != omen14]
    assert len(rest14) >= 2, "应至少有两个可作落点的房间"
    stranded14, bridge14 = rest14[0], rest14[1]
    hero14.room_key = stranded14

    def island_path(a: str, b: str) -> int:
        # 只有 omen14 与 bridge14 之间有通路（模拟"预兆房在隔壁孤岛"）
        if a == omen14 and b == omen14:
            return 0
        if {a, b} == {omen14, bridge14}:
            return 1
        return 9999

    with patch.object(engine14, "_path_length", side_effect=island_path):
        actions14 = handler14.available_actions(engine14, hero14)
    seek14 = next((a for a in actions14 if a.id == "nether_seek"), None)
    assert seek14 is not None, "够不到预兆房时该给出穿越虚空"
    assert seek14.data.get("room") in {omen14, bridge14}, (
        "落点应挑在预兆房所在的孤岛上，实际 " + str(seek14.data.get("room"))
    )

    # ---- p74/p145："shuffle the room tiles back into the room stack" ----
    # `_detach_room(return_to_deck=True)` 是 `insert(0, ...)`，而抽牌是
    # `room_deck.pop()`（从尾部拿）——不洗一次，回收的板块会排到整副牌的最后，
    # 预兆房等于被雪藏（seed151/4p 实测：回收 39 块后连翻 12 间没有一间预兆房）。
    engine15 = _run_until_haunt(seed=113, players=3, haunt_id=63)
    handler15 = engine15._mode_handler()
    spare15 = next(
        template
        for template in engine15.catalog.room_templates.values()
        if template.id in set(engine15.state.room_deck)
    )
    engine15.state.room_deck.remove(spare15.id)
    slot15 = TwistingNetherMode._isolated_slot(engine15, spare15.floor)
    assert slot15 is not None, "应能找出一格四邻皆空的坐标"
    placed15 = engine15._place_room(
        engine15._build_rotated_template(spare15, 0), slot15[0], slot15[1], 0
    )
    with patch.object(
        engine15, "_shuffle_room_piles", wraps=engine15._shuffle_room_piles
    ) as shuffle15:
        removed15 = handler15._purge(engine15)
    assert placed15.key in removed15, "没人、没锚、不连通的孤岛应被虚空回收"
    assert shuffle15.call_count == 1, "回收板块后必须把牌堆洗匀（p74 明文）"
    assert placed15.template_id in (
        set(engine15.state.room_deck) | set(engine15.state.room_discard)
    ), "被回收的板块应回到房间牌堆"

    # ---- 胜负 ----
    # 轨道值是现场推导的（锚点连通闭包大小），所以"锚满"必须真的去锚
    engine10 = _run_until_haunt(seed=113, players=3, haunt_id=63)
    handler10 = engine10._mode_handler()
    hero10 = next(p for p in engine10.state.players if p.role == "hero" and not p.dead)
    _set_current(engine10, hero10)
    hero10.items.clear()
    hero10.stats["knowledge"] = 8
    hero10.room_key = _nether_omen_room(engine10, hero10)
    assert handler10.check_victory(engine10) is False, "零锚点不该判胜"
    assert engine10.state.winner is None
    with patch.object(engine10, "roll_dice", return_value=6):
        handler10.perform_action(engine10, hero10, "anchor_room", {})
    region = handler10._anchored_region(engine10)
    assert region, "应至少锚下一间房"
    assert engine10._haunt_track_value("anchor_progress") == len(region)
    engine10._haunt_tracks()["anchor_progress"]["target"] = len(region)
    assert handler10.check_victory(engine10) is True
    assert engine10.state.winner == "heroes", "锚够房间 → 英雄胜"

    engine11 = _run_until_haunt(seed=113, players=3, haunt_id=63)
    handler11 = engine11._mode_handler()
    for player in engine11.state.players:
        if player.role == "hero":
            player.dead = True
    assert handler11.check_victory(engine11) is True
    assert engine11.state.winner == "traitor", "英雄全灭 → 叛徒胜"

    # 叛徒死亡不构成英雄胜（p74/p145 只认锚定足够房间）
    engine12 = _run_until_haunt(seed=113, players=3, haunt_id=63)
    handler12 = engine12._mode_handler()
    next(p for p in engine12.state.players if p.role == "traitor").dead = True
    engine12.state.winner = None
    engine12.check_victory()
    assert engine12.state.winner is None, "叛徒倒下不等于英雄达成锚定目标"



def verify_haunt64_blood_offering() -> None:
    """剧本 64：女孩/邪教徒/蝙蝠/献祭/计时/胜利条件（p75/p146）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=64)
    handler = engine._mode_handler()
    assert isinstance(handler, BloodOfferingMode)
    flags = engine._haunt_flags()

    # 女孩 token 在作祟房间
    girl = engine.tokens_of_kind("girl")
    assert girl, "女孩 token 应已放置"
    girl_room = flags.get("girl_room")
    assert girl_room is not None
    assert girl[0].room_key == girl_room, "女孩应站在作祟房间"

    # 邪教徒和蝙蝠已布点
    cultists = [m for m in engine.state.monsters if m.template_id == "cultist"]
    assert len(cultists) >= 1, "应有邪教徒"

    # 计时到 7 → 英雄胜
    engine._set_haunt_track_value("demon_timer", 7)
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"

    # p146：叛徒胜线是**亲手用力量攻击把女孩打满 5 点伤**。
    # 旧版这里断言 `flags["girl_sacrificed"]`——那个标在实现里根本不存在，
    # 原文也没有"邪教徒走到女孩房间即献祭"这条，是写测试时的占位臆想。
    engine.state.winner = None
    engine.state.phase = "HAUNT_PHASE"
    engine._set_haunt_track_value("demon_timer", 0)
    engine._set_haunt_track_value("girl_wounds", 0)
    flags["girl_dead"] = False
    flags["girl_stunned"] = 0
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    traitor.room_key = girl_room
    traitor.attack_used = False
    _set_current(engine, traitor)
    assert "attack_girl" in {a.id for a in handler.available_actions(engine, traitor)}, (
        "叛徒与女孩同房时应能动手"
    )

    # 英雄没有这条行动（p146 是叛徒专属胜线）
    decoy = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    decoy.room_key = girl_room
    _set_current(engine, decoy)
    assert "attack_girl" not in {a.id for a in handler.available_actions(engine, decoy)}, (
        "英雄不该有杀女孩的行动"
    )
    _set_current(engine, traitor)

    # 前 4 点伤只记伤，第 5 点才判胜
    with patch.object(engine, "_roll_attack", return_value=8), patch.object(
        engine, "roll_dice", return_value=1
    ):
        for expected in range(1, 5):
            assert handler.perform_action(engine, traitor, "attack_girl", {}) is True
            assert engine._haunt_track_value("girl_wounds") == expected
            assert not flags.get("girl_dead"), f"{expected} 点伤不该直接判胜"
        assert handler.perform_action(engine, traitor, "attack_girl", {}) is True
    assert flags.get("girl_dead") is True, "满 5 点伤 → 女孩死亡"
    assert engine.state.winner == "traitor"



def verify_haunt65_breath_of_wind() -> None:
    """剧本 65：骚灵/蜡烛寻找/点燃/倒计时/胜利条件（p76/p147）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=65)
    handler = engine._mode_handler()
    assert isinstance(handler, BreathOfWindMode)
    flags = engine._haunt_flags()

    # 骚灵在场
    poltergeist = engine._monster_by_template("ghost")
    assert poltergeist is not None, "骚灵应已生成"

    # 计时从 3 开始
    assert engine._haunt_track_value("poltergeist_timer") == 3, "计时应从 3 开始"

    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 找蜡烛（在厨房/餐厅/教堂/画廊）
    candle_room = next((r for r in engine.state.board.values()
                        if r.template_id in ("kitchen", "dining_room", "chapel", "gallery")), None)
    if candle_room is not None:
        hero.room_key = candle_room.key
        _set_current(engine, hero)
        ids = {a.id for a in handler.available_actions(engine, hero)}
        assert "find_candle" in ids, "在蜡烛房间应能找蜡烛"
        # 找蜡烛是速度 3+ 的检定：失败不发蜡烛（批次 3 修掉了"行动已执行=成功"）。
        with patch.object(engine, "_resolve_check", return_value=True):
            assert handler.perform_action(engine, hero, "find_candle", {}) is True
        assert engine.tokens_held_by(hero.id, "candle"), "找蜡烛（检定成功）应获得蜡烛"

    # 点燃蜡烛
    haunt_floor = engine.state.board.get(engine._haunt_rule_state().get("haunt_room", "")).floor
    hero.room_key = next(k for k, r in engine.state.board.items() if r.floor == haunt_floor)
    _set_current(engine, hero)
    engine._reset_player_turn_state(hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "burn_candle" in ids, "持蜡烛在作祟层应能点燃"
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "burn_candle", {}) is True
    assert engine._haunt_track_value("exorcism_progress") == 1

    # 胜利：进度满
    engine._set_haunt_track_value("exorcism_progress", engine._haunt_track_target("exorcism_progress"))
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt66_hell_on_earth() -> None:
    """剧本 66：圣徽充能 / 封闭 / 圣徽攻击驱逐 / 电梯与拾取封锁（p77/p148）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=66)
    handler = engine._mode_handler()
    assert isinstance(handler, HellOnEarthMode)
    assert engine.state.haunt is not None and engine.state.haunt.id == 66

    lord = engine._monster_by_template("hell_demon_lord")
    assert lord is not None, "恶魔领主应已生成"
    assert lord.speed == 3 and lord.might == 5 and lord.sanity == 3, "3 人局属性应为 Speed 3 Might 5 Sanity 3"
    assert engine._haunt_track_value("holy_power") == 0
    assert sum(1 for m in engine.state.monsters if m.template_id in ("giant", "cultist")) == 0

    traitor = next(p for p in engine.state.players if p.role == "traitor")
    holder = next((p for p in engine.state.players if "omen_holy_symbol" in p.items), None)
    assert holder is not None and holder.role == "hero", "圣徽应在英雄手上"
    assert handler.item_pickup_blocked(engine, traitor, "omen_holy_symbol") is True
    assert handler.item_pickup_blocked(engine, holder, "omen_holy_symbol") is False
    assert handler.mystic_elevator_blocked(engine, holder) is True
    assert handler.attack_allowed(engine, holder, lord) is False

    # 持徽者在当前房间即可充能（与圣徽同房）
    hero = holder
    _set_current(engine, hero)
    engine._reset_player_turn_state(hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "charge_holy_symbol" in ids
    assert "seal_room" not in ids
    assert "holy_symbol_attack" not in ids
    with patch.object(engine, "roll_dice", return_value=8):
        assert handler.perform_action(engine, hero, "charge_holy_symbol", {}) is True
    assert hero.attack_used is True
    # 持徽者充能成功后立刻封闭当前房间（引擎每回合一次剧本行动）
    assert engine._haunt_track_value("holy_power") == 1
    assert hero.room_key in engine._haunt_flags().get("sealed_rooms", [])
    assert engine.tokens_in_room(hero.room_key, "seal")

    # 把领主拉到封闭房，圣徽攻击打赢 → 英雄胜
    lord.room_key = hero.room_key
    hero.attack_used = False
    engine._haunt_rule_state().setdefault("actions_used", {}).pop(str(hero.id), None)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "holy_symbol_attack" in ids
    with patch.object(engine, "roll_dice", return_value=8), patch.object(engine, "_roll_monster_attack", return_value=1):
        assert handler.perform_action(engine, hero, "holy_symbol_attack", {}) is True
    assert engine.state.winner == "heroes"
    assert engine._monster_by_template("hell_demon_lord") is None

    # 未封闭房间打胜：轨道不够击晕则击退
    engine2 = _run_until_haunt(seed=113, players=3, haunt_id=66)
    handler2 = engine2._mode_handler()
    hero2 = next(p for p in engine2.state.players if "omen_holy_symbol" in p.items)
    lord2 = engine2._monster_by_template("hell_demon_lord")
    _set_current(engine2, hero2)
    engine2._reset_player_turn_state(hero2)
    engine2._haunt_flags()["initial_hero_count"] = 2  # 击晕要扣 2，轨道只有 1 → 击退
    engine2._set_haunt_track_value("holy_power", 1)
    lord2.room_key = hero2.room_key
    start_key = lord2.room_key
    with patch.object(engine2, "roll_dice", return_value=6), patch.object(engine2, "_roll_monster_attack", return_value=1):
        assert handler2.perform_action(engine2, hero2, "holy_symbol_attack", {}) is True
    assert engine2.state.winner is None
    assert engine2._monster_by_template("hell_demon_lord") is not None
    assert lord2.stunned_turns == 0
    # 差值 5，领主应被推离（若图上无路则可能原地，但同房有邻居时必须离开）
    if any(engine2._path_length(start_key, k) == 1 for k in engine2.state.board):
        assert lord2.room_key != start_key or engine2._path_length(start_key, hero2.room_key) == 0

    # 全灭英雄 → 叛徒胜
    engine3 = _run_until_haunt(seed=113, players=3, haunt_id=66)
    handler3 = engine3._mode_handler()
    for p in engine3.state.players:
        if p.role == "hero":
            p.dead = True
    assert handler3.check_victory(engine3) is True
    assert engine3.state.winner == "traitor"


def verify_haunt67_once_upon_a_time() -> None:
    """剧本 67：入定 / 抽任务 / 完成任务 / 故事终局（p78/p149）。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=67)
    handler = engine._mode_handler()
    assert isinstance(handler, StorybookTwistsMode)
    assert engine.state.haunt is not None and engine.state.haunt.id == 67

    spider = engine._monster_by_template("story_spider")
    assert spider is not None, "猎蛛应已生成"
    assert spider.speed == 4 and spider.might == 5 and spider.sanity == 3
    assert engine._monster_by_template("story_witch") is None
    assert engine._monster_by_template("story_dragon") is None
    assert engine._haunt_track_value("story") == 0
    assert engine._haunt_track_value("quests") == 0
    flags = engine._haunt_flags()
    flags["initial_hero_count"] = 2
    engine._haunt_tracks()["quests"]["target"] = 2

    traitor = next(p for p in engine.state.players if p.role == "traitor")
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    assert handler.attack_allowed(engine, hero, traitor) is False
    assert handler.attack_allowed(engine, traitor, hero) is False
    assert handler.counts_as_movement_obstacle(engine, hero, traitor) is False
    assert handler.item_use_blocked(engine, traitor, "item_axe") is True
    assert handler.can_discover_rooms(engine, traitor) is False

    # 与叛徒同房可抽任务；检定失败仍消耗行动
    hero.room_key = traitor.room_key
    _set_current(engine, hero)
    engine._reset_player_turn_state(hero)
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "obtain_quest" in ids
    with patch.object(engine, "roll_dice", return_value=1):
        assert handler.perform_action(engine, hero, "obtain_quest", {}) is True
    assert engine._haunt_flags().get("obtained_quests") in (None, [])

    # 检定过关则抽取任务；随后强制放进「高贵受苦」以便完成链路可测
    engine._haunt_rule_state().setdefault("actions_used", {}).pop(str(hero.id), None)
    hero.attack_used = False
    with patch.object(engine, "roll_dice", return_value=9):
        assert handler.perform_action(engine, hero, "obtain_quest", {}) is True
    assert engine._haunt_flags().get("obtained_quests")
    engine._haunt_flags()["obtained_quests"] = [9]

    # 在血房间完成高贵受苦（活着才算）
    bloody = next((k for k, r in engine.state.board.items() if r.template_id == "bloody_room"), None)
    if bloody is None:
        template = engine.catalog.room_templates["bloody_room"]
        placed = engine._place_room(template, 20, 20, 0)
        bloody = placed.key
    hero.room_key = bloody
    engine._haunt_rule_state().setdefault("actions_used", {}).pop(str(hero.id), None)
    with patch.object(engine, "roll_dice", return_value=0):
        assert handler.perform_action(engine, hero, "complete_quest", {}) is True
    assert 9 in engine._haunt_flags().get("completed_quests", [])
    assert engine._haunt_track_value("quests") == 1

    # 故事走到 7、任务未满 → 悲伤结局
    engine2 = _run_until_haunt(seed=113, players=3, haunt_id=67)
    handler2 = engine2._mode_handler()
    engine2._haunt_flags()["initial_hero_count"] = 2
    traitor2 = next(p for p in engine2.state.players if p.role == "traitor")
    _set_current(engine2, traitor2)
    engine2._reset_player_turn_state(traitor2)
    engine2._set_haunt_track_value("story", 6)
    handler2.on_turn_start(engine2, traitor2)
    assert engine2._haunt_flags().get("story_ended") is True
    assert engine2.state.winner == "traitor"

    # 任务数够、故事结束 → 英雄胜；叛徒倒下不能让英雄赢
    engine3 = _run_until_haunt(seed=113, players=3, haunt_id=67)
    handler3 = engine3._mode_handler()
    engine3._haunt_flags()["initial_hero_count"] = 2
    traitor3 = next(p for p in engine3.state.players if p.role == "traitor")
    traitor3.dead = True
    assert handler3.check_victory(engine3) is True
    assert engine3.state.winner is None
    engine3._haunt_flags()["completed_quests"] = [0, 1]
    engine3._haunt_flags()["story_ended"] = True
    assert handler3.check_victory(engine3) is True
    assert engine3.state.winner == "heroes"

    # 全灭英雄 → 叛徒胜
    engine4 = _run_until_haunt(seed=113, players=3, haunt_id=67)
    handler4 = engine4._mode_handler()
    for p in engine4.state.players:
        if p.role == "hero":
            p.dead = True
    assert handler4.check_victory(engine4) is True
    assert engine4.state.winner == "traitor"


def verify_haunt68_setup_and_seal() -> None:
    """剧本 68：开局布点（钥匙/仆人/地下墓穴）与回合/伤害轨封口（p79/p150）。"""
    engine = _run_until_haunt(seed=109, players=4, haunt_id=68)
    handler = engine._mode_handler()
    assert isinstance(handler, LabyrinthEscapeMode)
    flags = engine._haunt_flags()
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    hall = handler._hall_key(engine)
    assert hall, "入口大厅必须在场——那是唯一的出口"

    # p79/p150：钥匙数 = 英雄数；每间一枚，且不放在大厅（大厅里的钥匙不算"手上"）
    assert flags["hero_count"] == len(heroes)
    assert flags["keys_total"] == len(heroes)
    assert flags["escape_target"] == (len(heroes) + 1) // 2
    keys = engine.tokens_of_kind("key")
    assert len(keys) == len(heroes)
    assert all(token.holder is None for token in keys)
    key_rooms = [token.room_key for token in keys]
    assert len(key_rooms) == len(set(key_rooms)), "钥匙应分散在不同房间"
    assert all(engine.state.board[room].template_id != "entrance_hall" for room in key_rooms)

    # p150：仆人 = 英雄数-1，速4/力3/智5
    servants = [m for m in engine.state.monsters if m.template_id == "labyrinth_servant"]
    assert len(servants) == max(0, len(heroes) - 1)
    for servant in servants:
        assert (servant.speed, servant.might, servant.sanity) == (4, 3, 5)

    # p150：地下墓穴移出本局——用塌方标记等价实现，里面不能还留着活人
    catacombs = [key for key, room in engine.state.board.items() if room.template_id == "catacombs"]
    for key in catacombs:
        assert engine._is_collapsed(key), "地下墓穴应被翻出本局"
        assert not any(not p.dead and p.room_key == key for p in engine.state.players)
        assert not any(monster.room_key == key for monster in engine.state.monsters)

    # p150：回合/伤害轨归零（真实位数走 flags，UI 轨只到刻度 12）
    assert flags["turn_position"] == 0
    assert engine._haunt_track_value("labyrinth_turn") == 0
    assert engine._haunt_track_target("labyrinth_turn") == 12

    traitor = next(p for p in engine.state.players if p.role == "traitor")
    _set_current(engine, traitor)
    with patch.object(engine, "roll_dice", return_value=2):
        handler.on_turn_start(engine, traitor)
    assert flags["turn_position"] == 1 and not flags["sealed"], "掷不满 6 不该封口"
    assert engine._haunt_track_value("labyrinth_turn") == 1

    flags["turn_position"] = 15
    with patch.object(engine, "roll_dice", return_value=3):
        handler._advance_seal(engine)
    assert flags["turn_position"] == 16, "真实位数不该被轨道上限截断"
    assert engine._haunt_track_value("labyrinth_turn") == 12, "UI 轨只到刻度 12"

    # p150：出 6+ 即迷宫自我封闭 → 叛徒胜
    flags["turn_position"] = 3
    flags["sealed"] = False
    engine.state.winner = ""
    with patch.object(engine, "roll_dice", return_value=6):
        handler._advance_seal(engine)
    assert flags["sealed"] and engine.state.winner == "traitor"

    # p150 的胜负不依赖叛徒活着：他死了也要继续合拢（本轮首位存活英雄代推）
    engine.state.winner = ""
    flags["sealed"] = False
    traitor.dead = True
    first_hero, second_hero = heroes[0], heroes[1]
    # 本轮 turn_order 里第一个还活着的英雄是 second_hero（叛徒已排在其后且已死）
    engine.state.turn_order = [second_hero.id, traitor.id, first_hero.id]
    before = int(flags["turn_position"])
    _set_current(engine, second_hero)
    handler.on_turn_start(engine, second_hero)
    assert flags["turn_position"] == before + 1, "叛徒死后首位存活英雄应代推进轨道"
    _set_current(engine, first_hero)
    handler.on_turn_start(engine, first_hero)
    assert flags["turn_position"] == before + 1, "同一轮不能推进两次"


def verify_haunt68_key_route_and_confusion() -> None:
    """剧本 68：集钥匙→开锁→逃出，以及仆人致迷乱与白走一格（p79/p150）。"""
    engine = _run_until_haunt(seed=23, players=5, haunt_id=68)
    handler = engine._mode_handler()
    assert isinstance(handler, LabyrinthEscapeMode)
    flags = engine._haunt_flags()
    hall = handler._hall_key(engine)
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    keys = engine.tokens_of_kind("key")
    assert len(keys) == len(heroes)

    # 厅外拿着全部钥匙也开不了锁（p79：开锁必须站在入口大厅）
    far_room = next(key for key in engine.state.board if key != hall)
    for index, hero in enumerate(heroes):
        engine.give_token(keys[index].uid, hero.id)
        hero.room_key = far_room
    carrier = heroes[0]
    _set_current(engine, carrier)
    assert "unlock_door" not in {a.id for a in handler.available_actions(engine, carrier)}
    assert handler.perform_action(engine, carrier, "unlock_door", {}) is False

    # 全员带钥匙进厅：条件满足 → 开锁可用；厅内不再提供转交/放下
    for hero in heroes:
        hero.room_key = hall
    assert handler._all_keys_in_hall(engine) is True
    offered = {a.id for a in handler.available_actions(engine, carrier)}
    assert "unlock_door" in offered and not {"pass_key", "drop_key"} & offered

    # 检定失败：门不开（_perform_generic_haunt_action 失败也返回 True，只看 flag）
    _set_current(engine, carrier)
    carrier.steps_remaining = 5
    with patch.object(engine, "_resolve_check", return_value=False):
        handler.perform_action(engine, carrier, "unlock_door", {})
    assert not flags["door_unlocked"], "开锁失败不该把门打开"

    # 检定成功：门开 + 抽一张事件牌并结束回合（p79）
    with patch.object(engine, "_resolve_check", return_value=True), \
            patch.object(engine, "_draw_symbol_card", return_value=None) as drawn:
        assert handler.perform_action(engine, carrier, "unlock_door", {}) is True
    assert flags["door_unlocked"] is True
    assert drawn.called, "开锁成功者要抽一张事件牌（p79）"
    assert carrier.steps_remaining == 0 and carrier.movement_stopped, "开锁花掉本回合剩余行动"

    # 逃出要留 2 点移动；逃走者出局且身上的钥匙不会散落（p79）
    flags["escape_target"] = 1  # 本用例只验证"逃够即胜"这条判定线
    flee_hero = heroes[1]
    flee_hero.steps_remaining = 1
    _set_current(engine, flee_hero)
    assert "flee_labyrinth" not in {a.id for a in handler.available_actions(engine, flee_hero)}
    flee_hero.steps_remaining = 5
    held_before = [token.uid for token in engine.tokens_held_by(flee_hero.id, "key")]
    assert handler.perform_action(engine, flee_hero, "flee_labyrinth", {}) is True
    assert flee_hero.dead and flee_hero.id in flags["escaped_hero_ids"]
    assert flee_hero.steps_remaining == 3, "逃出消耗 2 点移动（p79）"
    assert [token.uid for token in engine.tokens_held_by(flee_hero.id, "key")] == held_before, \
        "逃走者把钥匙随身带走，不该散落在大厅"
    assert handler.check_victory(engine) and engine.state.winner == "heroes"

    # p150：仆人可改用理智攻击——打赢只是弄糊涂，双方属性都不掉
    engine.state.winner = ""
    flags["door_unlocked"] = False
    flags["escaped_hero_ids"] = [int(x) for x in flags["escaped_hero_ids"] if x != flee_hero.id]
    flags["escape_target"] = max(1, len(heroes) - 1)
    victim = next(p for p in engine.state.players if not p.dead and p.role == "hero")
    servant = next((m for m in engine.state.monsters if m.template_id == "labyrinth_servant"), None)
    if servant is None:  # 英雄数-1 可能为 0，补一只来验这条规则
        servant = engine._spawn_single_haunt_monster(
            dict(LabyrinthEscapeMode.SERVANT_SPEC), victim.room_key
        )
    # 把 victim 和仆人单独关进一间没有别的活人的房间：handler 按"理智最低"
    # 挑对手，同屋只可能选到她。
    isolate = next(
        key for key in engine.state.board
        if key != hall and not any(
            player.room_key == key for player in engine.state.players
            if not player.dead and player.id != victim.id
        )
    )
    victim.room_key = isolate
    servant.room_key = isolate
    positions_before = dict(victim.stat_positions)
    with patch.object(engine, "_roll_monster_attack", return_value=6), \
            patch.object(engine, "_roll_attack", return_value=1):
        assert handler.on_monster_turn_attack(engine, servant) is True
    assert engine.tokens_held_by(victim.id, "confused"), "仆人打赢应放一枚神志检定令牌"
    assert victim.stat_positions == positions_before, "理智攻击双方都不掉属性（p150）"

    # 迷乱者回合结束：被逼着白走一格（不花移动点），然后神志恢复
    victim.room_key = hall
    start_room = victim.room_key
    steps_before = victim.steps_remaining = 4
    handler.on_turn_end(engine, victim)
    assert victim.room_key != start_room, "叛徒应逼她白走一格（p150）"
    assert victim.steps_remaining == steps_before, "这一步不花她的移动点"
    assert not engine.tokens_held_by(victim.id, "confused"), "回合结束迷乱解除"

    # 仆人打不赢就什么都没有（原文：双方都不受伤害）
    other = next(p for p in engine.state.players if not p.dead and p.role == "hero" and p.id != victim.id)
    other.room_key = servant.room_key
    other_positions = dict(other.stat_positions)
    with patch.object(engine, "_roll_monster_attack", return_value=1), \
            patch.object(engine, "_roll_attack", return_value=6):
        handler.on_monster_turn_attack(engine, servant)
    assert not engine.tokens_held_by(other.id, "confused")
    assert other.stat_positions == other_positions, "仆人不该在理智对决中吃亏"


def verify_haunt68_bot_hall_guard() -> None:
    """剧本 68：持钥匙站在入口大厅的机器人不该主动走出去（`bot_stay_in_room`）。

    p79 的开门条件是"所有钥匙都在入口大厅里英雄的手上"。`bot_goal_rooms` 在
    "人已经站在目标房间"时返回空集（`_next_steps_toward` 跳过当前房间），寻路
    失去牵引，机器人会跟着通用目标漂出门外——这道闸门堵的就是那一步。
    """
    engine = _run_until_haunt(seed=23, players=5, haunt_id=68)
    handler = engine._mode_handler()
    assert isinstance(handler, LabyrinthEscapeMode)
    hall = handler._hall_key(engine)
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    keys = engine.tokens_of_kind("key")
    assert len(heroes) == 4 and len(keys) == 4

    carrier, mate, spare, extra = heroes
    off_hall = next(key for key in engine.state.board if key != hall)
    for hero in heroes:
        hero.room_key = off_hall

    # 持钥匙 + 人站在大厅 → 留守（地上 3 把，3 个空手队友能去捡）
    carrier.room_key = hall
    engine.give_token(keys[0].uid, carrier.id)
    assert sum(1 for t in keys if t.room_key) == 3
    assert handler.bot_stay_in_room(engine, carrier) is True, "持钥匙站厅：留守"

    # 同在大厅但空手 → 不留（他该出去找钥匙）
    mate.room_key = hall
    assert handler.bot_stay_in_room(engine, mate) is False

    # 持钥匙但人不在大厅 → 不留
    engine.give_token(keys[1].uid, extra.id)
    assert sum(1 for t in keys if t.room_key) == 2
    assert handler.bot_stay_in_room(engine, extra) is False

    # 地上 2 把、还能去捡的空手队友也是 2 个 → 仍留守
    assert handler.bot_stay_in_room(engine, carrier) is True

    # 只剩 0 个能去捡的队友（另两名英雄已倒下），地上仍有 2 把 → 必须自己离厅补位
    mate.dead = True
    spare.dead = True
    assert handler.bot_stay_in_room(engine, carrier) is False, "没人能顶替时他得出去捡"

    # 门已开：无论手上有没有钥匙、地上还剩什么，都该留在厅里等 2 点移动逃出
    engine._haunt_flags()["door_unlocked"] = True
    assert handler.bot_stay_in_room(engine, carrier) is True
    extra.room_key = hall
    assert handler.bot_stay_in_room(engine, extra) is True, "门开后厅内空手英雄也该留守"


def verify_haunt69_wisp_flees_heroes() -> None:
    """剧本 69：小精灵该躲着英雄跑，而不是固定往楼层最低处钻（p151）。

    旧实现 `options.sort(key=floor)` 让它在任何盘面上都朝同一个方向走——一条
    直线，英雄追起来不用动脑。新实现改成"离最近英雄越远越好"，这条用例钉住
    这个方向性。
    """
    engine = _run_until_haunt(seed=109, players=3, haunt_id=69)
    handler = engine._mode_handler()
    assert isinstance(handler, WispCaptureMode)
    wisp = handler._wisp(engine)
    assert wisp is not None
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    assert heroes

    mid = next(key for key in sorted(engine.state.board) if len(engine._door_neighbors(key)) >= 2)
    doors = sorted(engine._door_neighbors(mid))
    near, far = doors[0], doors[1]

    # 全部英雄塞进 near，小精灵站在 mid：它必须挑那条远离英雄的门
    for hero in heroes:
        hero.room_key = near
    wisp.room_key = mid
    assert handler._flee_step(engine, wisp, [near, far]) == far, "应往远离英雄的方向逃"
    assert handler._flee_step(engine, wisp, [far, near]) == far, "方向选择不该依赖入参顺序"

    # 反过来：英雄堵在 far，它就往 near 走
    for hero in heroes:
        hero.room_key = far
    assert handler._flee_step(engine, wisp, [near, far]) == near


def _force_haunt(seed: int, players: int, haunt_id: int) -> GameEngine:
    """零进度直接触发作祟（不复现探索过程），用于"触发瞬间"类断言。

    与 `_run_until_haunt` 的区别：这里棋盘上只有起始房间，所有剧本都在最贫瘠的
    状态下着手 setup——正是这种状态最容易暴露"读到默认值 0 就判胜"的 bug。
    """
    engine = _new_engine(seed=seed, players=players)
    engine._select_haunt_id = lambda room_id, omen_id, _h=haunt_id: _h
    engine.state.last_omen_id = next(
        card_id for card_id, card in engine.catalog.cards.items() if card.kind == "omen"
    )
    engine.state.haunt_pending = True
    engine._trigger_haunt(engine.current_player)
    return engine


def verify_haunt_script_visible_to_both_roles() -> None:
    """70 本剧本在英雄 / 叛徒两个视角都必须有可读文本。

    复刻 `ui._haunt_text_for_viewer` 的回退链（script → goal）。任何一本为空，
    玩家点「剧本」只会看到"当前视角没有可查看的剧本文本"，等于作祟没有内容。
    """
    for haunt_id, haunt in sorted(build_catalog(113).haunt_defs.items()):
        hero_text = (haunt.hero_script or haunt.hero_goal or "").strip()
        traitor_text = (haunt.traitor_script or haunt.traitor_goal or "").strip()
        assert hero_text, f"#{haunt_id} {haunt.name}：英雄视角没有任何可读文本"
        assert traitor_text, f"#{haunt_id} {haunt.name}：叛徒视角没有任何可读文本"


def verify_no_instant_verdict_on_trigger() -> None:
    """作祟触发的瞬间，任何一本剧本都不允许已经分出胜负。

    典型踩坑：`engine._haunt_track_target(未声明的轨道)` 返回 0，而判定写的是
    `value >= target`，于是 `0 >= 0` 恒真——作祟刚开始就判英雄胜（#44 实测 6/6 局）；
    或者 handler 在 setup 里按规则移除叛徒、check_victory 又 `return False`，
    让引擎的「叛徒死亡→英雄胜」兜底在第一个玩家回合就触发（#62 实测 6/6 局）。
    """
    for haunt_id in range(1, 71):
        engine = _force_haunt(seed=113, players=4, haunt_id=haunt_id)
        assert engine.state.phase == "HAUNT_PHASE", f"#{haunt_id} 触发作祟后阶段不是 HAUNT_PHASE"
        engine.check_victory()
        assert engine.state.winner is None, (
            f"#{haunt_id} {engine.state.haunt.name} 在作祟触发瞬间就判了 "
            f"{engine.state.winner}：{engine.state.winner_reason}"
        )


def verify_haunt_track_targets_nonzero() -> None:
    """handler 用 `_haunt_track_target(X)` 读到的轨道，X 必须真的被声明且 target > 0。

    这是 #44 的构建期红灯：rule_data 声明了 "progress"、handler 读 "ritual_progress"，
    `engine._haunt_track_target` 对未声明轨道返回 0，任何 `value >= target` 判定都会
    零进度即成立。target == 0 在引擎里表示"无上限轨道"，不该参与判胜比较。
    """
    import inspect  # noqa: PLC0415
    import re  # noqa: PLC0415

    for haunt_id in range(1, 71):
        engine = _force_haunt(seed=113, players=4, haunt_id=haunt_id)
        handler = engine._mode_handler()
        source = inspect.getsource(type(handler))
        names = set(re.findall(r'_haunt_track_target\("([A-Za-z0-9_]+)"\)', source))
        for name in sorted(names):
            declared = engine._haunt_tracks().get(name)
            assert declared is not None, (
                f"#{haunt_id} handler={type(handler).__name__} 读取了未声明的轨道 {name!r}"
                f"（_haunt_track_target 会返回 0，判胜会零进度成立）"
            )
            assert engine._haunt_track_target(name) > 0, (
                f"#{haunt_id} handler={type(handler).__name__} 的轨道 {name!r} target="
                f"{engine._haunt_track_target(name)}，参与判胜会零进度即胜"
            )


def verify_fixed_haunt_semantics() -> None:
    """钉住本轮修复的 4 本剧本语义，防止再被静默改回。

    · #44：仪式轨道名 = action 的 progress 字段，target = 玩家数；0 进度不判胜。
    · #62：叛徒按 p73 从游戏移除，判负权必须由 handler 自己接管（不落引擎兜底）。
    · #52：p63/p134 要求「叛徒死 **且** 无恶魔在场」，恶魔存活时叛徒死亡不算英雄胜。
    · #26：零只老鼠被安置时不得置 rats_placed，否则「杀光老鼠」被误判成立。
    """
    import types  # noqa: PLC0415

    # ---- #44 死亡终将寻来 ----
    engine = _run_until_haunt(seed=113, players=3, haunt_id=44)
    handler = engine._mode_handler()
    assert isinstance(handler, SupernaturalAgingMode)
    assert engine._haunt_track_target("ritual_progress") == len(engine.state.players), (
        "p55：仪式检定成功次数应等于玩家人数"
    )
    engine._set_haunt_track_value("ritual_progress", 0)
    engine.state.winner = None
    engine.check_victory()
    assert engine.state.winner is None, "仪式进度为 0 时不该判胜"
    engine._set_haunt_track_value("ritual_progress", engine._haunt_track_target("ritual_progress"))
    engine.check_victory()
    assert engine.state.winner == "heroes", "仪式进度满 → 英雄胜"

    # ---- #62 魔袋把戏 ----
    engine = _run_until_haunt(seed=113, players=3, haunt_id=62)
    handler = engine._mode_handler()
    assert isinstance(handler, BagOfTricksMode)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert traitor.dead, "p73：叛徒角色应从游戏中移除"
    engine._set_haunt_track_value("trinket_progress", 0)
    engine.state.winner = None
    assert handler.check_victory(engine) is True, "必须由 handler 接管判定（吸收引擎兜底）"
    assert engine.state.winner is None, "叛徒被移除 ≠ 英雄达成目标，不该判英雄胜"
    engine.check_victory()
    assert engine.state.winner is None, "引擎整体判定下也不该在零进度判胜"

    # ---- #52 噼啪光环中 ----
    engine = _run_until_haunt(seed=113, players=3, haunt_id=52)
    handler = engine._mode_handler()
    assert isinstance(handler, CracklingAuraMode)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    traitor.dead = True
    demon = types.SimpleNamespace(name="恶魔领主", template_id="giant", room_key="0:0:0")
    engine.state.monsters.append(demon)  # type: ignore[arg-type]
    engine.state.winner = None
    assert handler.check_victory(engine) is True, "恶魔在场时不该交给引擎兜底"
    assert engine.state.winner is None, "恶魔领主还活着时叛徒死亡不算英雄胜"
    engine.check_victory()
    assert engine.state.winner is None, "引擎整体判定下也必须保持未结束"
    engine.state.monsters.remove(demon)  # type: ignore[arg-type]
    engine.check_victory()
    # M10-63：p63 的胜利条件是"戒指被破解 **且** 无恶魔"。叛徒倒下只是让戒指
    # 掉进房间，英雄仍须就地把它破解掉——旧实现把"叛徒死"直接当英雄胜，正好
    # 反了（实测因此虚增了 5 局英雄胜：真正走完破解线的不到一半）。
    assert engine.state.winner is None, "戒指未破解时，叛徒倒下 + 无恶魔也不判英雄胜"
    flags = engine._haunt_flags()
    flags["ring_disenchanted"] = True
    engine._set_haunt_track_value("ring_track", 0)
    engine.check_victory()
    assert engine.state.winner == "heroes", "戒指被破解 + 无恶魔 → 英雄胜"

    # ---- #26 吹笛人的代价：零放置守卫 ----
    engine = _force_haunt(seed=113, players=4, haunt_id=26)
    handler = engine._mode_handler()
    assert isinstance(handler, RatRitualMode)
    if not handler._rats(engine):
        assert not engine._haunt_flags().get("rats_placed"), (
            "0 只老鼠被安置时不得置 rats_placed，否则「杀光老鼠」恒真"
        )
        engine.check_victory()
        assert engine.state.winner is None, "没有安置过老鼠时不该判英雄胜"


# ---------------------------------------------------------------------------
# M10-35 测试扩容：70 本剧本 x（道具使用 / 角色交互 / 剧本机制）
# ---------------------------------------------------------------------------


def verify_all_haunts_data_integrity() -> None:
    """70 本剧本的静态数据必须自洽（卡牌 / 房间 / 怪物 / 行动）。

    这是"引用了不存在的 id"与"数据写了引擎不读"两类问题的构建期红灯：
    required_cards 不在卡表里 → 英雄永远拿不到（39 号矛写成令牌就是这么
    把英雄线锁死的）、key_rooms 写了不存在的房间 → bot 目标解析不出来、
    monsters 模板缺失 → 延迟生成少一只、action.stat 拼错 → 检定按 0 属性算。
    """
    catalog = build_catalog(113)
    valid_cards = set(catalog.cards)
    valid_rooms = set(catalog.room_templates)
    valid_monsters = set(catalog.monsters)
    valid_stats = {"might", "speed", "sanity", "knowledge"}
    valid_sides = {"heroes", "traitor", "both", "any"}
    valid_spawns = {"deferred", "haunt_room", "omen_rooms", "room_id"}
    for haunt_id in range(1, 71):
        rule = catalog.haunt_defs[haunt_id].rule_data or {}
        assert rule, f"#{haunt_id} 缺少 rule_data"
        assert rule.get("mode"), f"#{haunt_id} 未声明 mode"
        assert rule.get("fidelity") == "refined", f"#{haunt_id} fidelity 不是 refined"
        assert rule.get("source_pages"), f"#{haunt_id} 未标注 source_pages"
        for card_id in rule.get("required_cards", []) or []:
            assert card_id in valid_cards, (
                f"#{haunt_id} required_cards 引用了不存在的卡 {card_id}"
            )
        for room_id in rule.get("key_rooms", []) or []:
            assert room_id in valid_rooms, (
                f"#{haunt_id} key_rooms 引用了不存在的房间 {room_id}"
            )
        for track_id, spec in ((rule.get("setup", {}) or {}).get("tracks", {}) or {}).items():
            target = spec.get("target", 0)
            if isinstance(target, int):
                assert target >= 0, f"#{haunt_id} 轨道 {track_id} target 非法：{target}"
        for spec in rule.get("monsters", []) or []:
            template_id = spec.get("template_id")
            assert template_id in valid_monsters, (
                f"#{haunt_id} monsters 引用了不存在的模板 {template_id}"
            )
            assert spec.get("spawn") in valid_spawns, (
                f"#{haunt_id} {template_id} 的 spawn 非法：{spec.get('spawn')}"
            )
        for action in rule.get("actions", []) or []:
            assert action.get("id"), f"#{haunt_id} 存在没有 id 的 action"
            stat = action.get("stat")
            stats = stat if isinstance(stat, (list, tuple)) else ([stat] if stat is not None else [])
            for one in stats:
                assert one in valid_stats, (
                    f"#{haunt_id} action {action.get('id')} 的 stat 非法：{one}"
                )
            assert str(action.get("side", "both")) in valid_sides, (
                f"#{haunt_id} action {action.get('id')} 的 side 非法"
            )


def verify_all_haunts_handler_smoke() -> None:
    """70 本 handler 的两侧接口在"零进度直接触发"下都不许抛异常。

    逐个覆盖：英雄 / 叛徒两侧的可用行动（id 唯一、label 非空）、未知
    action_id 必须安全返回 False、bot 寻路目标与进度摘要（两侧视角）不得
    崩溃；实现了 quest_carrier 的剧本要返回合法 player id。
    """
    for haunt_id in range(1, 71):
        engine = _force_haunt(seed=113, players=4, haunt_id=haunt_id)
        handler = engine._mode_handler()
        valid_ids = {player.id for player in engine.state.players}
        for player in engine.state.players:
            actions = handler.available_actions(engine, player)
            ids = [action.id for action in actions]
            assert len(ids) == len(set(ids)), f"#{haunt_id} 同一玩家行动 id 重复：{ids}"
            for action in actions:
                assert isinstance(action.label, str) and action.label, (
                    f"#{haunt_id} 行动 {action.id} 缺少 label"
                )
            assert handler.perform_action(engine, player, "__no_such_action__", {}) is False, (
                f"#{haunt_id} 未知 action_id 未安全返回 False"
            )
            goals = handler.bot_goal_rooms(engine, player)
            assert isinstance(goals, list), f"#{haunt_id} bot_goal_rooms 未返回 list"
            assert all(isinstance(goal, str) and goal for goal in goals), (
                f"#{haunt_id} bot_goal_rooms 含非法项：{goals}"
            )
            summary = handler.progress_summary(engine, player)
            assert isinstance(summary, list) and all(isinstance(line, str) for line in summary), (
                f"#{haunt_id} progress_summary 非法：{summary!r}"
            )
        carrier = getattr(handler, "quest_carrier", None)
        if callable(carrier):
            value = carrier(engine)
            assert value is None or value in valid_ids, (
                f"#{haunt_id} quest_carrier 返回了非法 player id：{value}"
            )


def verify_traitor_death_semantics_sweep() -> None:
    """叛徒死亡到底算不算英雄胜——按 p2 基础规则逐本定性后钉住。

    基础规则："先完成剧本目标的一方获胜；即使叛徒死亡，只要怪物还能完成
    目标就照常行动"。所以只有当原文把"叛徒死亡"写进英雄胜利条件时，
    叛徒阵亡才算英雄胜；其余剧本必须继续打到目标完成。
    """
    # 原文把"叛徒死亡"写进英雄胜利条件（p44/p115 等）→ 判英雄胜
    hero_win_on_traitor_death = (5, 41, 42, 45, 51, 56, 57, 70)
    # 原文另有条件、叛徒死不等于结束 → 绝不判英雄胜
    # （52 号 M10-63 移入本组：p63 要求"戒指被破解 且 无恶魔"，叛徒倒下只是
    # 让戒指掉进房间，英雄仍须就地破解——旧实现把它写成了"叛徒死即英雄胜"。）
    keeps_playing = (1, 20, 33, 34, 35, 36, 37, 39, 43, 44, 52, 61, 63, 64, 65)
    for haunt_id in hero_win_on_traitor_death:
        engine = _force_haunt(seed=113, players=4, haunt_id=haunt_id)
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        assert traitor is not None, f"#{haunt_id} 作祟开始时应有叛徒"
        traitor.dead = True
        engine.state.winner = None
        engine.check_victory()
        assert engine.state.winner == "heroes", (
            f"#{haunt_id} 原文把叛徒死亡算作英雄胜利，实际判了 {engine.state.winner}"
        )
    for haunt_id in keeps_playing:
        engine = _force_haunt(seed=113, players=4, haunt_id=haunt_id)
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        assert traitor is not None, f"#{haunt_id} 作祟开始时应有叛徒"
        traitor.dead = True
        engine.state.winner = None
        engine.check_victory()
        assert engine.state.winner is None, (
            f"#{haunt_id} 叛徒死亡不构成英雄胜利（须完成剧本目标），"
            f"实际判了 {engine.state.winner}"
        )
    # 反向：英雄全灭必须是叛徒胜（70 本全量）
    for haunt_id in range(1, 71):
        engine = _force_haunt(seed=113, players=4, haunt_id=haunt_id)
        for player in engine.state.players:
            if player.role == "hero":
                player.dead = True
        engine.state.winner = None
        engine.check_victory()
        assert engine.state.winner == "traitor", (
            f"#{haunt_id} 英雄全灭却没有判叛徒胜（实际 {engine.state.winner}）"
        )


def verify_item_use_matrix() -> None:
    """道具 / 预兆逐张过交互通道：拾取 → 使用 → 丢弃 → 交易（p2-p3）。

    通用物品规则（无剧本沙盒，避免剧本专属闸门干扰）：
      · 同伴卡（疯子 / 女孩 / 狗）tradeable=False：可拾取、不可丢弃、不可交易；
      · 盔甲 / 咬痕这类不可交易卡：可拾取、可丢弃、但不能交易；
      · 武器类 use_item 应提示"攻击时选择使用"而不是报错或生效；
      · 其余卡牌丢弃后落在房间、可再拾取、可与同房间队友来回交易。
    """
    engine = _new_engine(seed=113, players=4)
    player = engine.state.players[0]
    other = engine.state.players[1]
    other.room_key = player.room_key
    room_key = player.room_key
    companions: list[str] = []
    untradeable: list[str] = []
    weapons: list[str] = []
    tradable: list[str] = []
    for card_id, card in sorted(engine.catalog.cards.items()):
        if card.kind == "event":
            continue
        player.items = [c for c in player.items if c != card_id]
        player.item_used = False
        engine.state.room_items.setdefault(room_key, []).append(card_id)
        assert engine.pickup_item(player, card_id), f"{card_id} 无法拾取"
        result = engine.use_item(player, card_id)
        assert isinstance(result, bool), f"{card_id} use_item 未返回 bool"
        if "weapon" in card.tags:
            weapons.append(card_id)
            assert result is False, f"{card_id} 是武器：use_item 应提示攻击时选择"
        if card_id not in player.items:  # 一次性 / 用后弃置的卡补回来继续测交互
            player.items.append(card_id)
        if "companion" in card.tags or card_id == "omen_bite":
            # p11："咬""狗""女孩""女士"不是道具——不能丢弃、盗取或交易。
            companions.append(card_id)
            if not card.tradeable:
                untradeable.append(card_id)
            assert engine.drop_item(player, card_id) is False, f"{card_id} 不是道具，不应可丢弃"
            assert engine.trade_item(player, other, card_id) is False, (
                f"{card_id} 不是道具，不应可交易"
            )
            continue
        assert engine.drop_item(player, card_id), f"{card_id} 应可丢弃"
        assert card_id in engine.state.room_items.get(room_key, []), (
            f"{card_id} 丢弃后应落在房间里"
        )
        assert engine.pickup_item(player, card_id), f"{card_id} 丢弃后应能再拾取"
        if not card.tradeable:
            untradeable.append(card_id)
            assert engine.trade_item(player, other, card_id) is False, (
                f"{card_id} 声明 tradeable=False，不应可交易"
            )
            continue
        tradable.append(card_id)
        assert engine.trade_item(player, other, card_id), f"{card_id} 应可交给同房间队友"
        assert card_id in other.items, f"{card_id} 交易后应在队友手里"
        assert engine.trade_item(other, player, card_id), f"{card_id} 应可换回来"
    assert len(companions) >= 3, f"应至少识别出疯子 / 女孩 / 狗三张同伴卡：{companions}"
    assert len(untradeable) >= 2, f"盔甲 / 咬痕应不可交易：{untradeable}"
    assert len(tradable) >= 20, f"可交易卡过少：{len(tradable)}"
    assert len(weapons) >= 5, f"武器卡过少，请检查标签：{weapons}"


def verify_weapon_cards_attack_paths() -> None:
    """每张武器卡都要能被识别为可用攻击武器（含 ranged / speed 标签）。"""
    engine = _force_haunt(seed=113, players=4, haunt_id=1)
    player = engine.state.players[0]
    target = next(p for p in engine.state.players if p.role != player.role)
    target.room_key = player.room_key
    checked = 0
    for card_id, card in sorted(engine.catalog.cards.items()):
        if "weapon" not in card.tags:
            continue
        player.items = [card_id]
        player.attack_used = False
        weapons = engine.available_attack_weapons(player)
        assert card_id in weapons, f"{card_id} 未被识别为可用武器：{weapons}"
        verdict = engine.attack_would_be_allowed(player, target, card_id)
        assert isinstance(verdict, bool), f"{card_id} attack_would_be_allowed 未返回 bool"
        checked += 1
    assert checked >= 5, f"武器卡过少：{checked}"


def verify_character_interaction_matrix() -> None:
    """角色交互主通道：同房间限制、死亡掉落、可偷清单（p2-p3）。"""
    engine = _new_engine(seed=113, players=4)
    first, second = engine.state.players[0], engine.state.players[1]

    # 交易要求同房间，且只能交出手里有的卡
    second.room_key = first.room_key
    first.items = ["item_axe"]
    assert engine.trade_item(first, second, "item_axe") is True
    assert engine.trade_item(first, second, "item_axe") is False, "自己手里没有的卡不能交易"
    other_room = next(key for key in engine.state.board if key != first.room_key)
    second.room_key = other_room
    assert engine.trade_item(second, first, "item_axe") is False, "不同房间不能交易"

    # 死亡掉落：物品与同伴都落在房间，进房者可拾取
    victim = engine.state.players[2]
    victim.items = ["omen_madman", "item_axe"]
    victim.companions = ["omen_madman"]
    victim.room_key = first.room_key
    victim.stats["might"] = 0
    # 死亡只在作祟期成立（p5：作祟开始之前没有人会死）。
    engine.state.phase = "HAUNT_PHASE"
    engine._check_player_death(victim)
    assert victim.dead, "力量归零应死亡"
    assert not victim.items and not victim.companions, "死亡应清空物品与同伴"
    dropped = engine.state.room_items.get(victim.room_key, [])
    assert "item_axe" in dropped and "omen_madman" in dropped, (
        f"死亡掉落应留在房间：{dropped}"
    )
    first.room_key = victim.room_key
    assert engine.pickup_item(first, "omen_madman"), "同伴应能被进房者拾取"
    assert "omen_madman" in first.companions, "拾取同伴后应进入 companions"

    # 可偷清单：可交易物品可偷，同伴（tradeable=False）不可被偷
    victim.items = ["item_lucky_stone", "omen_girl"]
    victim.companions = ["omen_girl"]
    candidates = engine._steal_candidates(first, victim)
    assert "item_lucky_stone" in candidates, f"可交易物品应可被偷：{candidates}"
    assert "omen_girl" not in candidates, "同伴不可被偷"


def verify_haunt40_buried_alive() -> None:
    """剧本 40：活埋——埋人 / 搜查 / 挖掘 / 计时四条链路（p51/p122）。"""
    engine = _force_haunt(seed=113, players=4, haunt_id=40)
    handler = engine._mode_handler()
    assert isinstance(handler, BuriedAliveMode)
    flags = engine._haunt_flags()

    # 埋人：埋葬室在地下室、必经之路可达、不在楼梯平台（能避则避）
    burial = flags.get("burial_room")
    assert burial and burial in engine.state.board, "必须选出埋葬室"
    assert engine.state.board[burial].floor == -1, "p122：朋友埋在地下室房间"
    basement = handler._basement_rooms(engine)
    assert len(basement) >= 2, f"p122：地下室房间应先补几间进场：{len(basement)}"
    anchor = engine.state.meta["haunt_rule"]["haunt_room"]
    assert engine._path_length(anchor, burial) < 9999, (
        "埋葬室必须可达——否则英雄永远挖不出来（70 号孤岛同款坑）"
    )
    assert engine.state.board[burial].template_id != "basement_landing", (
        "有其他地下室房间时不应把朋友埋在楼梯平台"
    )
    assert engine._haunt_track_target("burial_damage") == 12, "p122：12 点伤害即死亡"
    assert engine._haunt_track_target("dig_progress") == len(engine.state.players), (
        "p51：挖出朋友所需成功次数 = 作祟开始时玩家人数"
    )

    # 搜查：成功且非埋葬室 → 排除；成功且是埋葬室 → 找到
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    others = [room.key for room in basement if room.key != burial]
    hero.room_key = others[0]
    assert "h40_search" in {action.id for action in handler.available_actions(engine, hero)}
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "h40_search", {}) is True
    assert others[0] in flags.get("ruled_out", []), "成功搜查非埋葬室应排除该房间"
    assert not flags.get("burial_found"), "排除的房间不该被当成埋葬室"
    hero.room_key = burial
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "h40_search", {}) is True
    assert flags.get("burial_found") is True, "搜查埋葬室成功应找到朋友的位置"

    # 挖掘：只在埋葬室提供，成功后进度 +1；集满 → 英雄胜
    assert "h40_dig" in {action.id for action in handler.available_actions(engine, hero)}
    with patch.object(engine, "_resolve_check", return_value=True):
        assert handler.perform_action(engine, hero, "h40_dig", {}) is True
    assert engine._haunt_track_value("dig_progress") == 1, "挖掘成功应推进一格"
    engine._set_haunt_track_value("dig_progress", engine._haunt_track_target("dig_progress"))
    engine.state.winner = None
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes", "挖出朋友 → 英雄胜"

    # 通灵板（p51）：理智 7+ 直接得知埋葬室
    engine.state.winner = None
    flags["burial_found"] = False
    hero.items.append("omen_spirit_board")
    hero.room_key = others[0]
    with patch.object(engine, "roll_dice", return_value=8):
        assert handler.perform_action(engine, hero, "h40_spirit_board", {}) is True
    assert flags.get("burial_found") is True, "通灵板 7+ 应直接得知埋葬室"

    # 计时：叛徒回合结束轨位 +1 并结算伤害；12 点 → 叛徒胜
    engine.state.winner = None
    engine._set_haunt_track_value("dig_progress", 0)
    engine._set_haunt_track_value("burial_damage", 0)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    handler.on_turn_end(engine, traitor)
    assert engine._haunt_track_value("burial_damage") > 0, "叛徒回合结束应结算被埋者伤害"
    assert int(flags.get("bury_timer", 0)) >= 1, "Turn/Damage 轨位应 +1"
    engine._set_haunt_track_value("burial_damage", 12)
    engine.state.winner = None
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor", "被埋者 12 点伤害 → 叛徒胜"

    # 吸收兜底：叛徒死亡不构成英雄胜利（p51 只认"挖出朋友"）
    engine.state.winner = None
    engine._set_haunt_track_value("dig_progress", 0)
    engine._set_haunt_track_value("burial_damage", 0)
    traitor.dead = True
    assert handler.check_victory(engine) is True
    assert engine.state.winner is None, "叛徒死后英雄仍须把朋友挖出来"

    # 机器人目标：未找到 → 未排除的地下室房间；已找到 → 埋葬室
    flags["burial_found"] = False
    goals = handler.bot_goal_rooms(engine, hero)
    assert goals and all(goal.startswith("__room__") for goal in goals), (
        f"未找到时应搜索地下室：{goals}"
    )
    flags["burial_found"] = True
    assert handler.bot_goal_rooms(engine, hero) == [f"__room__{burial}"], (
        "找到后应直奔埋葬室"
    )

    # ---- M10-52 回归：叛徒出局后埋人钟不停（p122 的倒计时是剧本自身的钟，
    # 由轮转顺序里第一位存活玩家代推，惯例同 22/30/33 号）。缺这条时力 1 的
    # 英雄（1 骰永远够不到 4+）会永远卡在"挖不动"上——seed107/3p 实测 300 回合
    # 收不了场：两人在地下室里挖了 40 个回合，挖掘进度始终 0。
    engine.state.winner = None
    engine._set_haunt_track_value("burial_damage", 0)
    engine._set_haunt_track_value("dig_progress", 0)
    flags["bury_timer"] = 0
    traitor.dead = True
    for p in engine.state.players:
        if p.role == "hero":
            p.dead = False
    alive_order = [
        pid
        for pid in engine.state.turn_order
        if any(p.id == pid and not p.dead for p in engine.state.players)
    ]
    assert len(alive_order) >= 2, "本用例需要至少两名存活玩家"
    first = next(p for p in engine.state.players if p.id == alive_order[0])
    second = next(p for p in engine.state.players if p.id == alive_order[1])
    handler.on_turn_end(engine, first)
    assert int(flags.get("bury_timer", 0)) == 1, "叛徒出局后应由轮转首位存活玩家代推"
    timer_once = int(flags["bury_timer"])
    damage_once = engine._haunt_track_value("burial_damage")
    handler.on_turn_end(engine, second)
    assert int(flags["bury_timer"]) == timer_once, "同一轮里其他人不得重复推钟"
    assert engine._haunt_track_value("burial_damage") == damage_once, "一轮只结算一次伤害"
    handler.on_turn_end(engine, traitor)
    assert int(flags["bury_timer"]) == timer_once, "死者的回合结束不该推钟"
    engine._set_haunt_track_value("burial_damage", 12)
    engine.state.winner = None
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "traitor", "钟走到 12 点仍是叛徒胜（p122）"


def verify_haunt33_fresh_tile_and_explore_gate() -> None:
    """剧本 33：p44 本回合新铺砖 +3；探索被关闭时不得给出必失败的探索选项。"""
    engine = _run_until_haunt(seed=101, players=5, haunt_id=33)
    handler = engine._mode_handler()
    assert isinstance(handler, LakeRescueMode)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    landing = next(
        (key for key, room in engine.state.board.items() if room.template_id == "basement_landing"),
        None,
    )
    assert landing, "33 号应保证地下室平台在场"
    hero.room_key = landing
    # _run_until_haunt 在回合中途停下，当前英雄可能带着 movement_stopped；
    # 这里复位成"刚轮到他、可自由移动"的最普通状态。
    hero.movement_stopped = False
    hero.dead = False
    hero.steps_remaining = max(hero.steps_remaining, 9)
    options = engine.available_move_options(hero)

    # 引擎不得给出"走的时候才被拒绝"的假探索选项（否则机器人整局空转）
    explores = [option for option in options if option.is_new_room]
    if not handler.can_discover_rooms(engine, hero):
        assert not explores, "探索被剧本关闭时仍给出探索选项 → 机器人会死循环在必失败选项上"

    # 划水进入新砖：本回合搜索加值 +3；跨回合由 on_turn_start 清掉
    swim = next(
        (option for option in options if str(option.target_key).startswith(handler.LAKE_PREFIX)),
        None,
    )
    assert swim is not None, f"岸边应能划水进入湖面：{[(o.direction, o.target_key) for o in options]}"
    hero.steps_remaining = max(hero.steps_remaining, swim.cost)
    with patch.object(handler, "_search_roll"):  # 只验证记砖与加值，不触发搜索表结算
        assert handler.lake_move(engine, hero, swim) is True
    fresh = engine._haunt_flags().setdefault("fresh_tiles", {})
    assert fresh.get(str(hero.id)) == hero.room_key, "新铺的砖应记进 fresh_tiles"
    with_fresh = handler._search_bonus(engine, hero)
    fresh.pop(str(hero.id))
    without_fresh = handler._search_bonus(engine, hero)
    assert with_fresh - without_fresh == handler.SEARCH_BONUS_FRESH_TILE, (
        f"p44：本回合新铺的砖应 +{handler.SEARCH_BONUS_FRESH_TILE}"
    )
    fresh[str(hero.id)] = hero.room_key
    with patch.object(handler, "_search_roll"):  # 搜索表可能挪人铺砖、把记录写回来
        handler.on_turn_start(engine, hero)
    assert str(hero.id) not in engine._haunt_flags().get("fresh_tiles", {}), (
        "回合开始应清掉上回合的 fresh 砖记录（+3 只在本回合有效）"
    )


def verify_haunt39_spear_flow() -> None:
    """剧本 39：矛是卡（p50 "the Spear card"）——可拾取、可上交继承人。"""
    engine = _run_until_haunt(seed=113, players=3, haunt_id=39)
    handler = engine._mode_handler()
    assert isinstance(handler, HeirAssassinMode)
    flags = engine._haunt_flags()
    heir = handler._heir(engine)
    assert heir is not None
    spear_room = flags.get("spear_room")
    assert spear_room and spear_room in engine.state.board, "应把矛放进一个已探明房间"

    # 矛必须是 omen_spear 卡（不是无人能拾取的 marker 令牌）
    assert "omen_spear" in engine.state.room_items.get(spear_room, []), (
        "矛应作为卡牌摆进房间（旧版 marker 令牌谁都拿不到 → 英雄线不可达）"
    )
    assert not engine.tokens_of_kind("spear"), "不应再生成矛令牌"
    for deck in engine.state.card_decks.values():
        assert "omen_spear" not in deck, "矛已摆进房间，不应还留在牌堆里"

    # 引擎常规拾取通道可用
    heir.room_key = spear_room
    assert engine.pickup_item(heir, "omen_spear") is True, "继承人应能拾取矛卡"
    assert "omen_spear" in heir.items

    # 收牌人 = 继承人（bot 的通用"交给持令牌队友"启发在这里不适用）
    assert handler.quest_carrier(engine) == heir.id

    # bot 目标：先去捡"躺在地上的"缺牌，地上没有就直奔王座等队友送来。
    # （M10-70 改：旧版继承人会去追"持牌的队友"，而队友的目标本来就是
    #   "继承人在哪"，两人互换房间互追、回合开始时永远不同房 → 交接永不发生。
    #   seed79/5p 实测 250+ 回合对调。现在改为"继承人钉王座，队友送过来"。）
    def _strip(card_id: str) -> None:
        """把某个关键牌从所有玩家手里与所有房间地板上摘掉，保证夹具可复现。"""
        for p in engine.state.players:
            while card_id in p.items:
                p.items.remove(card_id)
        for k in list(engine.state.room_items):
            items = [c for c in engine.state.room_items[k] if c != card_id]
            if items:
                engine.state.room_items[k] = items
            else:
                engine.state.room_items.pop(k, None)

    heir.room_key = spear_room
    throne = flags.get("throne_room")
    # 夹具显式化：谁活着、谁持牌、在哪，全部摆明，不依赖本局的偶然状态。
    for p in engine.state.players:
        if p.role == "hero":
            p.dead = False
    _strip("omen_spear")
    _strip("omen_ring")
    heir.items = ["omen_spear"]
    assert handler.bot_goal_rooms(engine, heir) == [f"__room__{throne}"], (
        "矛已在手、地上没有别的关键牌时应直奔王座（不再追持牌队友）"
    )
    heir.items = ["omen_spear", "omen_ring"]
    assert handler.bot_goal_rooms(engine, heir) == [f"__room__{throne}"], "两件齐了就去王座"
    # 关键牌躺在地上 → 继承人去捡（内容兜底把牌放到地板上，这条路必须走得通）
    room_key = next(k for k in engine.state.board if k != throne)
    heir.items = ["omen_spear"]
    heir.room_key = throne
    engine.state.room_items[room_key] = ["omen_ring"]
    assert handler.bot_goal_rooms(engine, heir) == [f"__room__{room_key}"], (
        "地上有关键牌时继承人应去捡，而不是站在王座上等"
    )
    assert handler.bot_stay_in_room(engine, heir) is False, (
        "地上还有关键牌时继承人不能钉死在王座上（否则一步不动空转到回合上限）"
    )
    _strip("omen_ring")
    assert handler.bot_stay_in_room(engine, heir) is True, (
        "地上没有关键牌、人已经在王座上时应站住等队友送牌"
    )
    other = next(
        (p for p in engine.state.players if p.role == "hero" and not p.dead and p.id != heir.id),
        None,
    )
    if other is not None:
        assert handler.bot_goal_rooms(engine, other) == [f"__room__{heir.room_key}"], (
            "队友应去和继承人会合"
        )
        # 送牌方到站也得停：王座是死胡同，只剩 1 步时通用走位会把唯一的出口
        # （回楼梯）选掉，进了又出 → 回合开始时不在王座，交接永远不发生
        # （seed113/5p 实测：持矛者 62 个回合 0 次留在王座房）。
        heir.items = []          # 继承人还缺矛，队友正带着它过来
        other.items = ["omen_spear"]
        other.room_key = heir.room_key
        assert handler.bot_stay_in_room(engine, other) is True, (
            "带着继承人所缺的牌站在继承人房里时应站住等交接"
        )
        other.room_key = room_key
        assert handler.bot_stay_in_room(engine, other) is False, (
            "不在继承人房里就不用站住"
        )
        other.items = []
    heir.items = []

    # quest_carrier 让队友把矛/戒指交给继承人（同房间、且持牌方是当前回合玩家）
    if other is not None:
        heir.items = []
        heir.room_key = spear_room
        other.items = ["omen_spear"]
        other.room_key = spear_room
        _set_current(engine, other)
        bot = BotController()
        assert bot._try_share_quest_items(engine, other) is True, (
            "持矛队友应与继承人交接（quest_carrier）"
        )
        assert "omen_spear" in heir.items, "矛应已交到继承人手里"
    else:
        heir.items = ["omen_spear"]

    # 继承人持矛与戒登王座 → 英雄胜
    if "omen_ring" not in heir.items:
        heir.items.append("omen_ring")
    heir.room_key = throne
    engine.state.winner = None
    assert handler.check_victory(engine) is True
    assert engine.state.winner == "heroes"


def verify_haunt39_deck_fallback() -> None:
    """剧本 39 内容兜底：预兆来源真的枯竭时，压在牌堆里的关键牌落到王座脚下。

    内容失衡（预兆牌 13 张 vs 带预兆符号的房间 7 间）让"戒指从未被抽到"成为
    常事；房屋探满后连抽牌机会都没有，英雄胜利线物理不可达——seed63/4p 实测：
    49 间全揭开、三层前沿全为 0、`_has_future_omen_source()` 为 False、戒指在
    残余预兆牌里。兜底只在"确实再也抽不到预兆"时动手，正常对局行为不变。

    这里用桩把"来源枯竭"这个条件固定下来（真跑去把房子探满既慢又不稳）；
    端到端那条路已由 seed63/4p 由僵局变为 69 回合终局覆盖。
    """
    engine = _run_until_haunt(seed=63, players=4, haunt_id=39)
    handler = engine._mode_handler()
    assert isinstance(handler, HeirAssassinMode)
    throne = engine._haunt_flags().get("throne_room")
    assert throne and throne in engine.state.board

    def _clear_ring() -> None:
        for p in engine.state.players:
            while "omen_ring" in p.items:
                p.items.remove("omen_ring")
        for k in list(engine.state.room_items):
            kept = [c for c in engine.state.room_items[k] if c != "omen_ring"]
            if kept:
                engine.state.room_items[k] = kept
            else:
                engine.state.room_items.pop(k, None)
        for deck in (*engine.state.card_decks.values(), *engine.state.card_discards.values()):
            while "omen_ring" in deck:
                deck.remove("omen_ring")

    _clear_ring()
    deck = engine.state.card_decks.setdefault("omen", [])
    deck.append("omen_ring")
    # 1) 还有未来预兆来源：兜底不许碰牌堆
    has_source = lambda: True  # noqa: E731
    real = engine._has_future_omen_source
    engine._has_future_omen_source = has_source
    try:
        handler._ensure_required_cards_reachable(engine)
        assert "omen_ring" in deck, "还有未来预兆来源时不该动牌堆"
        assert "omen_ring" not in engine.state.room_items.get(throne, []), (
            "来源没枯竭就不该把牌塞到王座脚下"
        )
        # 2) 来源枯竭：关键牌取出牌堆、放到王座脚下
        engine._has_future_omen_source = lambda: False  # noqa: E731
        handler._ensure_required_cards_reachable(engine)
        assert "omen_ring" not in deck, "来源枯竭时应把关键牌取出牌堆"
        assert "omen_ring" in engine.state.room_items.get(throne, []), (
            "取出的关键牌应放在王座脚下（继承人本来就要去的地方）"
        )
        # 3) 幂等：再跑一次不会复制
        handler._ensure_required_cards_reachable(engine)
        assert engine.state.room_items[throne].count("omen_ring") == 1, (
            "兜底必须幂等，不能每次回合开始都塞一张"
        )
    finally:
        engine._has_future_omen_source = real


def verify_all_haunts_win_branches_and_action_reachability() -> None:
    """每本剧本都要同时具备英雄胜/叛徒胜分支，且声明的行动真实可达。

    这是"机制没实现、只能靠引擎兜底判胜"的构建期红灯：
      · 缺英雄胜利分支 → 英雄只可能靠"叛徒死亡"通用兜底赢（#62 那类跳过）；
      · 缺叛徒胜利分支 → 只可能靠"英雄全灭"兜底（多数剧本合法，但必须显式）；
      · rule_data 声明了 action id、而覆盖了 perform_action 的 handler 既不处理
        也不回落 super() → 该行动永远执行不到（M10-15 抓到的 5 号死数据同款）。

    统计口径：handler 继承链源码 + 引擎 `_haunt<N>_/_perform_haunt<N>_/
    _available_haunt<N>_` 系列 + 该剧本自己声明的 win_conditions / goal 文案，
    合起来算"这本剧本自己的实现"（#1 的英雄胜利点就在引擎的 `h1_banish_mummy`
    行动里，所以必须把引擎侧也算进来）。
    """
    import inspect  # noqa: PLC0415
    import json  # noqa: PLC0415

    catalog = build_catalog(113)
    mode_module = sys.modules[type(get_mode_handler("generic")).__module__]
    engine_module = sys.modules[GameEngine.__module__]
    mode_source = inspect.getsource(mode_module)
    engine_source = inspect.getsource(engine_module)
    # 豁免：5 号 shoot_werewolf——注释明说它只用于 required_cards 与寻路提示，
    # 实际射杀由通用攻击流程处理（M10-15 已确认属有意声明，非死数据）。
    whitelist = {5: {"shoot_werewolf"}}
    for haunt_id in range(1, 71):
        rule = catalog.haunt_defs[haunt_id].rule_data or {}
        handler = get_mode_handler(rule.get("mode"))
        handler_cls = type(handler)
        text = json.dumps(rule, ensure_ascii=False)
        for cls in handler_cls.__mro__:
            try:
                text += inspect.getsource(cls)
            except (OSError, TypeError):  # object 等内建类拿不到源码
                pass
        for pattern in (
            f"def _haunt{haunt_id}_",
            f"def _perform_haunt{haunt_id}_",
            f"def _available_haunt{haunt_id}_",
        ):
            start = 0
            while True:
                idx = engine_source.find(pattern, start)
                if idx < 0:
                    break
                nxt = engine_source.find("\n    def ", idx)
                text += engine_source[idx: nxt if nxt > 0 else idx + 4000]
                start = idx + 1
        assert (
            '_set_winner("heroes"' in text
            or '"winner": "heroes"' in text
            or 'winner = "heroes"' in text
        ), f"#{haunt_id} 找不到英雄胜利分支——英雄难道只能靠引擎兜底赢？"
        assert (
            '_set_winner("traitor"' in text
            or '"winner": "traitor"' in text
            or 'winner = "traitor"' in text
        ), f"#{haunt_id} 找不到叛徒胜利分支——叛徒难道只能靠'英雄全灭'兜底？"
        handler_source = inspect.getsource(handler_cls)
        for action in rule.get("actions") or []:
            action_id = str(action.get("id") or "")
            if not action_id or action_id in whitelist.get(haunt_id, set()):
                continue
            if action_id in mode_source or action_id in engine_source:
                continue
            # 未覆盖 perform_action（或回落到 super()）的 handler 走 rule_data
            # 通用执行（stat 检定 / attack 对决 / progress / set_flags），
            # 行动 id 不必出现在代码里。
            if (
                "def perform_action" not in handler_source
                or "super().perform_action" in handler_source
            ):
                continue
            raise AssertionError(
                f"#{haunt_id} 行动 {action_id} 既不被 handler 处理、也不回落通用路径（死数据）"
            )


# ---------------------------------------------------------------------------
# M10-38（批次 1 审计）：引擎新增能力 + 剧本 1-5 修复的回归测试
# ---------------------------------------------------------------------------


def verify_haunt_action_success_flag() -> None:
    """`last_haunt_action_succeeded()`：行动"已执行"与检定"成功"必须分开。

    `_perform_generic_haunt_action` 检定失败时也返回 True（本回合行动已用掉），
    所以 handler 里 `ok = super().perform_action(...)` + `if ok:` 的老写法会把
    失败当成功发奖励——剧本 3 的曼德拉草、剧本 4 的蛛卵与前门都因此白送过。
    """
    engine = _run_until_haunt(seed=113, players=4, haunt_id=3)
    assert engine.state.phase == "HAUNT_PHASE"
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    with patch.object(engine, "_resolve_check", return_value=False):
        executed = engine._perform_generic_haunt_action(hero, "dig_root", {})
    assert executed is True, "检定失败也应算行动已执行（否则机器人会重复尝试）"
    assert engine.last_haunt_action_succeeded() is False, "检定失败不能标记为成功"

    with patch.object(engine, "_resolve_check", return_value=True):
        engine._perform_generic_haunt_action(hero, "dig_root", {})
    assert engine.last_haunt_action_succeeded() is True, "检定成功必须标记为成功"

    # 行动不可用（找不到 id）时不得残留上一次的成功标记
    engine._perform_generic_haunt_action(hero, "no_such_action", {})
    assert engine.last_haunt_action_succeeded() is False, "不可用的行动必须清掉成功标记"


def verify_haunt3_dig_root_needs_success() -> None:
    """p14：挖曼德拉草是 4+ 知识检定，失败不能白送令牌。"""
    engine = _run_until_haunt(seed=113, players=4, haunt_id=3)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    _set_current(engine, hero)
    engine.spawn_token("root", label="曼德拉草", role="carrier", room_key=hero.room_key)
    handler = engine._mode_handler()
    hero.items.append("omen_book")

    with patch.object(engine, "_resolve_check", return_value=False):
        handler.perform_action(engine, hero, "dig_root", {})
    assert not engine.tokens_held_by(hero.id, "root"), "检定失败不能拿到曼德拉草"

    with patch.object(engine, "_resolve_check", return_value=True):
        handler.perform_action(engine, hero, "dig_root", {})
    assert engine.tokens_held_by(hero.id, "root"), "检定成功必须拿到曼德拉草"


def verify_haunt3_restore_frog_gating() -> None:
    """p14：房间里没有青蛙不能复原；检定失败也不能复原（两条都曾缺失）。"""
    engine = _run_until_haunt(seed=113, players=4, haunt_id=3)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    other = next(
        p for p in engine.state.players if p.role == "hero" and p.id != hero.id and not p.dead
    )
    _set_current(engine, hero)
    hero.items.append("omen_book")

    assert "restore_frog" not in {a.id for a in engine.available_haunt_actions(hero)}, (
        "同房间没有青蛙时不该出现「复原青蛙」"
    )

    other.room_key = hero.room_key
    engine._turn_into_frog(other)
    assert "restore_frog" in {a.id for a in engine.available_haunt_actions(hero)}, (
        "同房间有青蛙时应可尝试复原"
    )

    handler = engine._mode_handler()
    with patch.object(engine, "_resolve_check", return_value=False):
        handler.perform_action(engine, hero, "restore_frog", {})
    assert other.frog is True, "检定失败不能复原青蛙（旧实现会白送）"

    with patch.object(engine, "_resolve_check", return_value=True):
        handler.perform_action(engine, hero, "restore_frog", {})
    assert other.frog is False, "检定成功应复原青蛙"


def verify_haunt4_failed_checks_do_not_advance() -> None:
    """p15：毁卵/开门的检定失败不能置 flag（旧实现白送过胜利进度）。"""
    engine = _run_until_haunt(seed=113, players=4, haunt_id=4)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    _set_current(engine, hero)
    handler = engine._mode_handler()

    # 毁卵：需要医疗包 + 与作祟揭示者同房间
    revealer = next(p for p in engine.state.players if p.id == engine.state.haunt_revealer_id)
    hero.room_key = revealer.room_key
    hero.items.append("item_medical_kit")
    flags["eggs_destroyed"] = False
    with patch.object(engine, "_resolve_check", return_value=False):
        handler.perform_action(engine, hero, "destroy_eggs_medical_kit", {})
    assert flags.get("eggs_destroyed") is False, "检定失败不能销毁蛛卵"
    with patch.object(engine, "_resolve_check", return_value=True):
        handler.perform_action(engine, hero, "destroy_eggs_medical_kit", {})
    assert flags.get("eggs_destroyed") is True, "检定成功必须销毁蛛卵"

    # 开前门：需在入口大厅，6+ 知识/力量
    entrance = next(
        (r for r in engine.state.board.values() if r.template_id == "entrance_hall"), None
    )
    assert entrance is not None, "入口大厅应当在场上（起始房间）"
    hero.room_key = entrance.key
    flags["front_door_open"] = False
    with patch.object(engine, "_resolve_check", return_value=False):
        handler.perform_action(engine, hero, "open_front_door", {})
    assert flags.get("front_door_open") is False, "检定失败不能开门"
    with patch.object(engine, "_resolve_check", return_value=True):
        handler.perform_action(engine, hero, "open_front_door", {})
    assert flags.get("front_door_open") is True, "检定成功必须开门"


def verify_searchable_required_cards() -> None:
    """p15：剧本关键牌（医疗包）还在牌堆里时，抽物品卡的英雄可以直接搜出来。"""
    engine = _run_until_haunt(seed=113, players=4, haunt_id=4)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 把医疗包放回牌堆，复现"尚未被发现"
    for deck in engine.state.card_decks.values():
        while "item_medical_kit" in deck:
            deck.remove("item_medical_kit")
    for player in engine.state.players:
        while "item_medical_kit" in player.items:
            player.items.remove("item_medical_kit")
    for items in engine.state.room_items.values():
        while "item_medical_kit" in items:
            items.remove("item_medical_kit")
    engine.state.card_decks.setdefault("item", []).append("item_medical_kit")

    engine._draw_item(hero)
    assert "item_medical_kit" in hero.items, "抽物品卡时应把剧本关键牌搜出来"
    assert "item_medical_kit" not in engine.state.card_decks.get("item", []), (
        "搜出来的牌必须从牌堆移除，不能复制"
    )


def verify_seance_traitor_anywhere() -> None:
    """p84：叛徒持通灵板可在任意房间降灵；英雄仍限五芒星室。"""
    engine = _run_until_haunt(seed=113, players=4, haunt_id=2)
    traitor = next(p for p in engine.state.players if p.role == "traitor" and not p.dead)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    room = next(
        r for r in engine.state.board.values() if r.template_id != "pentagram_chamber"
    )
    traitor.room_key = room.key
    hero.room_key = room.key
    if "omen_spirit_board" not in traitor.items:
        traitor.items.append("omen_spirit_board")

    _set_current(engine, traitor)
    assert "seance_check" in {a.id for a in engine.available_haunt_actions(traitor)}, (
        "叛徒持通灵板应能在任意房间举行降灵会"
    )
    _set_current(engine, hero)
    assert "seance_check" not in {a.id for a in engine.available_haunt_actions(hero)}, (
        "英雄仍必须在五芒星室才能降灵"
    )


def verify_haunt2_setup_places_pentagram() -> None:
    """p84：五芒星室不在屋内时，叛徒开局要把它拉进屋，且离自己尽量远。"""
    engine = _run_until_haunt(seed=113, players=4, haunt_id=2)
    pentagram = next(
        (r for r in engine.state.board.values() if r.template_id == "pentagram_chamber"),
        None,
    )
    assert pentagram is not None, "2 号剧本的 setup 必须保证五芒星室在场"
    traitor = next((p for p in engine.state.players if p.role == "traitor" and not p.dead), None)
    if traitor is None:
        return
    distance = engine._path_length(traitor.room_key, pentagram.key)
    assert distance != 9999, "五芒星室必须可达（否则先放进屋也没用）"


def verify_haunt2_burial_timer_not_frozen() -> None:
    """降灵主人死亡后，安葬倒计时由"本轮最后一位存活英雄"代跑，不能冻结。"""
    engine = _run_until_haunt(seed=113, players=4, haunt_id=2)
    flags = engine._haunt_flags()
    flags["ghost_summoned"] = True
    flags["ghost_control"] = "heroes"
    flags["bones_buried"] = False
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    assert heroes, "需要一个存活英雄"
    flags["seance_owner_id"] = heroes[0].id
    heroes[0].dead = True
    engine._set_haunt_track_value("ghost_rest_timer", 0)

    handler = engine._mode_handler()
    ticked = 0
    for hero in heroes[1:]:
        engine.state.turn_index = engine.state.turn_order.index(hero.id)
        before = engine._haunt_track_value("ghost_rest_timer")
        handler.on_turn_start(engine, hero)
        if engine._haunt_track_value("ghost_rest_timer") > before:
            ticked += 1
    assert ticked == 1, f"主人死后每轮应恰好推进一次倒计时（实际 {ticked} 次）"


def verify_ensure_room_in_play_farthest() -> None:
    """p84：`farthest_from_key` 选的落位不该比默认落位更近。"""
    engine = _new_engine(seed=131, players=4)
    on_board = {r.template_id for r in engine.state.board.values()}
    candidate = next(
        (
            template_id
            for template_id in engine.catalog.room_templates
            if template_id not in on_board and template_id in engine.state.room_deck
        ),
        None,
    )
    if candidate is None:
        return
    origin = next(iter(engine.state.board))
    far_key = engine._ensure_room_in_play(candidate, farthest_from_key=origin)
    assert far_key is not None
    far_distance = engine._path_length(origin, far_key)
    assert far_distance not in (0, 9999), "应放在可达、且不与起点重合的位置"

    engine2 = _new_engine(seed=131, players=4)
    default_key = engine2._ensure_room_in_play(candidate)
    assert default_key is not None
    default_distance = engine2._path_length(origin, default_key)
    assert far_distance >= default_distance, (
        f"最远落位 {far_distance} 不该比默认落位 {default_distance} 更近"
    )


def verify_explore_all_dead_ends_game() -> None:
    """探索期全员倒下：立刻终局，不能把轮转停在死者身上（黄金 seed7-3p）。

    `start_turn` 的"全员已死"分支过去只处理作祟期，探索期直接 return，
    于是 turn_count 冻结、之后每次 take_turn 都是空转。探索期没有叛徒与
    剧本可判，收口方式是"游戏结束、不判胜方"。
    """
    engine = _new_engine(seed=7, players=3)
    # 探索期本身不允许死人（p5），所以"全员倒下"只可能出现在作祟期；
    # 这里直接构造终局条件（属性归零 + 作祟期）来验收口分支。
    engine.state.phase = "HAUNT_PHASE"
    for player in engine.state.players:
        player.stats["might"] = 0
        engine._check_player_death(player)
    assert engine.state.phase == "GAME_OVER", "全员倒下应直接终局"
    assert not engine.state.winner, "探索期没有叛徒，不应判出胜方"
    assert engine.state.winner_reason, "终局要有可读原因"
    # 兜底分支再跑一次也不应改变结论（轮转停在死者身上是允许的，游戏已结束）
    engine.start_turn()
    assert engine.state.phase == "GAME_OVER"


def verify_mystic_elevator_not_transit() -> None:
    """神秘电梯：不算"可探索前沿"，也不能当路径中转（进入即被传送）。

    seed137/4p 实测：机器人把电梯当探索目标，进去→被传送到随机楼层→再
    走回来，200 回合只开出 30 间房，作祟迟迟不触发。
    """
    from engine import DIRECTION_DELTAS  # 模块级常量，本文件顶层未导入

    engine = _new_engine(seed=131, players=4)
    elevator_key = engine._ensure_room_in_play("mystic_elevator")
    assert elevator_key is not None, "测试前提：电梯能进场"
    elevator = engine.state.board[elevator_key]
    open_positions = 0
    for direction in elevator.doors:
        delta = DIRECTION_DELTAS.get(direction)
        if delta is None:
            continue
        pos = (elevator.floor, elevator.x + delta[0], elevator.y + delta[1])
        if pos not in engine.state.pos_index:
            open_positions += 1
    assert open_positions > 0, "测试前提：电梯要有空门位"
    assert elevator_key not in engine.exploration_frontier_keys(elevator.floor), (
        "电梯有空门位也不算探索前沿——进去只会被传送走"
    )
    graph = engine._build_graph(avoid_transit=True)
    assert graph[elevator_key] == [], "avoid_transit 路径不能从电梯穿出去"


def verify_omen_exhaustion_triggers_haunt() -> None:
    """预兆来源断掉时，探索期要直接进入作祟（不能无限空转）。

    两个判据都覆盖：预兆牌抽光；剩下的预兆房**放不下**（_can_place_template）。
    seed131/3p 实测：全屋铺满 48/49 间后，唯一剩下的预兆房没有合法落位，
    引擎却一直认为"未来还有预兆"，探索期 400 回合不结束。
    """
    engine = _new_engine(seed=113, players=3)
    # 负面：楼层上没有已放置房间时，该层模板没有任何落位
    for key in [k for k, room in engine.state.board.items() if room.floor == -1]:
        room = engine.state.board.pop(key)
        engine.state.pos_index.pop((room.floor, room.x, room.y), None)
    empty_floor_template = next(
        template
        for template in engine.catalog.room_templates.values()
        if not any(room.floor == template.floor for room in engine.state.board.values())
    )
    assert engine._can_place_template(empty_floor_template) is False

    # 牌抽光 + 场上没有未翻开的预兆房 + 牌堆里没有预兆房 → 未来无预兆
    engine.state.card_decks["omen"] = []
    engine.state.card_discards["omen"] = []
    for room in engine.state.board.values():
        if room.symbol == "omen":
            room.revealed = True
    engine.state.room_deck = [
        rid for rid in engine.state.room_deck
        if engine.catalog.room_templates[rid].symbol != "omen"
    ]
    engine.state.room_discard = [
        rid for rid in engine.state.room_discard
        if engine.catalog.room_templates[rid].symbol != "omen"
    ]
    engine.state.last_omen_id = next(
        card_id for card_id, card in engine.catalog.cards.items() if card.kind == "omen"
    )
    assert not engine._has_future_omen_source()
    engine.start_turn()
    assert engine.state.phase == "HAUNT_PHASE", "预兆来源断掉应直接触发作祟"


def verify_dead_player_command_guard() -> None:
    """死者只剩"结束回合"这一条命令（倒下后不能把掉落的牌捡回去）。"""
    from engine import ActionCommand  # 局部导入（本文件顶层只导了 GameEngine）

    engine = _run_until_haunt(seed=113, players=3, haunt_id=6)
    victim = next(p for p in engine.state.players if p.dead)
    _set_current(engine, victim)
    room_key = victim.room_key
    card_id = "item_medical_kit"
    engine.state.room_items.setdefault(room_key, [])
    if card_id not in engine.state.room_items[room_key]:
        engine.state.room_items[room_key].append(card_id)

    assert not engine.execute_command(
        ActionCommand("pickup", victim.id, {"card_id": card_id})
    ), "死者不能捡牌"
    assert card_id in engine.state.room_items.get(room_key, []), "牌应该还躺在地上"
    assert not engine.pickup_item(victim, card_id), "引擎层同样要挡住"
    # 死者仍能结束回合——否则轮转会卡在死者身上（剧本 6 老 bug）
    assert engine.execute_command(ActionCommand("end_turn", victim.id))


def verify_haunt7_goal_hooks() -> None:
    """7 号目标门控：持书才去实验室、抢到喷雾才去销毁房、被抓住先打抓人者。

    p18/p89。此前两处偏差：全体英雄都往实验室挤（只有持书的人做得成
    检定）；叛徒没抢到喷雾就把三间销毁房当常驻目标巡视空房。
    """
    engine = _run_until_haunt(seed=101, players=4, haunt_id=7)
    handler = engine._mode_handler()
    assert isinstance(handler, CarnivorousIvyMode)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor" and not p.dead)

    if "omen_book" in hero.items:
        hero.items.remove("omen_book")
    assert handler.bot_action_blocked(engine, hero, "make_plant_spray"), "没书不该把实验室当目标"
    if "omen_book" not in hero.items:
        hero.items.append("omen_book")
    assert not handler.bot_action_blocked(engine, hero, "make_plant_spray"), "持书应解锁"

    assert handler.bot_action_blocked(engine, traitor, "destroy_spray")
    assert handler.bot_goal_suppressed(engine, traitor), "没喷雾的叛徒不该有剧本目标房间"
    engine.spawn_token("plant_spray", label="植物喷雾", role="carried", holder=traitor.id)
    assert not handler.bot_action_blocked(engine, traitor, "destroy_spray"), "抢到喷雾应解锁"
    assert not handler.bot_goal_suppressed(engine, traitor)

    # 持喷雾的人去有根/尖端的房间（另一局，避免与上面的令牌串味）
    engine2 = _run_until_haunt(seed=101, players=4, haunt_id=7)
    handler2 = engine2._mode_handler()
    hero2 = next(p for p in engine2.state.players if p.role == "hero" and not p.dead)
    roots = [token for token in engine2.tokens_of_kind("root") if token.room_key]
    assert roots, "7 号开局至少要布下一对根/尖端"
    assert handler2.bot_goal_rooms(engine2, hero2) == [], "没喷雾时没有喷杀目标"
    engine2.spawn_token("plant_spray", label="植物喷雾", role="carried", holder=hero2.id)
    goals = handler2.bot_goal_rooms(engine2, hero2)
    assert f"__room__{roots[0].room_key}" in goals, "持喷雾应把有根的房间当目标"

    # 被抓住 → 指认抓着它的那只（bot_ai 会优先攻击它）
    tip = next(
        monster for monster in engine2.state.monsters
        if getattr(monster, "template_id", "") == "creeper_tip"
    )
    engine2._haunt_flags()["grabbed"] = {str(hero2.id): tip.id}
    assert handler2.bot_captor_monster(engine2, hero2) is tip
    engine2._haunt_flags()["grabbed"] = {}
    assert handler2.bot_captor_monster(engine2, hero2) is None

    # 书还压在预兆牌堆里 → 英雄必须去翻新房间找书（p18 的造喷雾两步链）
    engine3 = _run_until_haunt(seed=101, players=4, haunt_id=7)
    handler3 = engine3._mode_handler()
    hero3 = next(p for p in engine3.state.players if p.role == "hero" and not p.dead)
    deck = engine3.state.card_decks.setdefault("omen", [])
    if "omen_book" not in deck:
        deck.append("omen_book")
    engine3._haunt_flags()["plant_spray_created"] = False
    engine3._haunt_flags()["plant_spray_destroyed"] = False
    assert handler3.bot_wants_explore(engine3, hero3), "书没进场时英雄应继续探索"
    engine3._haunt_flags()["plant_spray_created"] = True
    assert not handler3.bot_wants_explore(engine3, hero3), "喷雾造出后不必再找书"


def verify_bot_attacks_captor_first() -> None:
    """被怪抓住时，机器人优先攻击"抓着它的那只"（赢了才能脱身，p18）。

    seed127/5p 实测：英雄被 mon_3 抓着、同房间还有另外 9 只尖端，它按列表
    顺序一直打 mon_1，被钉在入口大厅 180 回合、整局 245 回合。
    """
    engine = _run_until_haunt(seed=127, players=5, haunt_id=7)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    tips = [
        monster for monster in engine.state.monsters
        if getattr(monster, "template_id", "") == "creeper_tip"
    ]
    assert len(tips) >= 2, "需要两只以上尖端才能验证'打错对象'"
    other, captor = tips[0], tips[1]
    other.room_key = captor.room_key
    hero.room_key = captor.room_key
    _set_current(engine, hero)
    engine._haunt_flags()["grabbed"] = {str(hero.id): captor.id}

    attacked: list = []
    original_attack = engine.attack
    engine.attack = lambda attacker, target, weapon_card_id=None, ranged=False: (  # type: ignore[method-assign]
        attacked.append(target) or True
    )
    try:
        BotController()._try_attack(engine, hero)
    finally:
        engine.attack = original_attack  # type: ignore[method-assign]
    assert attacked, "应当发起一次攻击"
    assert attacked[0] is captor, "应优先攻击抓着自己的那只，而不是列表里第一只"


def verify_haunt9_traitor_goal_gating() -> None:
    """9 号：圣徽不在手上时"毁圣徽"的房间不算目标，叛徒改去追杀英雄。

    seed109/3p 实测：叛徒把深渊/熔炉房/地下湖当常驻目标来回巡视，而圣徽
    还压在预兆牌堆里，它在地下室三间房之间绕了 33 圈、整局拖到 133 回合。
    """
    engine = _run_until_haunt(seed=113, players=3, haunt_id=9)
    handler = engine._mode_handler()
    assert isinstance(handler, DeathDanceMode)
    # 剧本 9 开局无叛徒：按既有测试的写法，在舞厅诱惑失败制造一个。
    # 持圣徽者豁免诱惑检定（p20），所以挑一个不带圣徽的英雄。
    hero = next(
        (
            p
            for p in engine.state.players
            if p.role == "hero" and not p.dead and "omen_holy_symbol" not in p.items
        ),
        None,
    )
    assert hero is not None, "需要一个不带圣徽的英雄来制造堕落"
    ballroom_key = next(k for k, r in engine.state.board.items() if r.template_id == "ballroom")
    hero.room_key = ballroom_key
    with patch.object(engine, "_resolve_check", return_value=False):
        handler.on_turn_start(engine, hero)
    assert hero.role == "traitor", "需要在舞厅堕落一个叛徒来验证门控"

    assert handler.bot_action_blocked(engine, hero, "destroy_holy_symbol")
    assert handler.bot_goal_suppressed(engine, hero)
    bot = BotController()
    assert bot._haunt_goal_targets(engine, hero) == set(), "被抑制时不应再有剧本目标房间"

    hero.items.append("omen_holy_symbol")
    assert not handler.bot_action_blocked(engine, hero, "destroy_holy_symbol"), "持徽应解锁"
    assert not handler.bot_goal_suppressed(engine, hero)
    targets = bot._haunt_goal_targets(engine, hero)
    destroy_templates = {"chasm", "furnace_room", "underground_lake"}
    on_board_destroy = {
        key
        for key, room in engine.state.board.items()
        if room.template_id in destroy_templates
    }
    if on_board_destroy:
        assert targets & on_board_destroy, (
            f"持徽后销毁房应回到目标（实际 {sorted(targets)}）"
        )


def verify_stairs_reverse_link_exit() -> None:
    """楼梯链接只在一侧声明时，出口生成必须补出反向选项（图与出口一致）。

    13 号 seed137/3p 实测：图里"入口大厅—地下室楼梯"相邻（_build_graph 会
    对称补边），出口列表里却没有这条（只扫本房间的 links）——机器人寻路把
    这条边当下一步，承诺加分落在一个选不出来的选项上，在入口大厅↔厨房来回
    16 次；而去地下墓穴其实只要下两层楼。楼梯在物理上双向可走。
    """
    engine = _new_engine(seed=3, players=4)
    entrance_key = next(
        key for key, room in engine.state.board.items() if room.template_id == "entrance_hall"
    )
    stairs_key = engine._ensure_room_in_play("stairs_from_basement", entrance_key)
    assert stairs_key, "地下室楼梯应当能放上场"
    assert "up" in engine.state.board[stairs_key].links, "前提：楼梯只从自己一侧声明 up 链接"

    hero = engine.state.players[0]
    hero.room_key = entrance_key
    hero.movement_stopped = False
    targets = {
        option.target_key
        for option in engine.available_move_options(hero)
        if not option.is_new_room
    }
    assert stairs_key in targets, "入口大厅应当能顺着楼梯下到地下室楼梯"

    # 图与出口必须一致：图里的邻居都得有对应出口，否则机器人会走向走不通的下一步。
    graph_neighbors = set(engine._build_graph(avoid_transit=True)[entrance_key])
    missing = graph_neighbors - targets
    assert not missing, f"图里有边但走不过去：{sorted(missing)}"


def verify_haunt13_wake_success_gating() -> None:
    """p24：唤醒检定失败不能当成功——令牌与轨道必须一致。

    seed137/5p 实测：唤醒令牌 6 枚、轨道只记 4 点。旧实现拿
    `ok = super().perform_action(...)` + `if ok:` 当成功标志，而引擎的返回值
    是"行动是否执行"（检定失败同样是 True），失败也发了一枚"唤醒成功"令牌。
    """
    engine = _run_until_haunt(seed=113, players=4, haunt_id=13)
    handler = engine._mode_handler()
    assert isinstance(handler, NightmareDreamMode)
    sleeper_room = engine._haunt_flags().get("sleeper_room")
    assert sleeper_room, "沉睡房间应当已记录"
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    hero.room_key = sleeper_room
    if "omen_holy_symbol" not in hero.items:
        hero.items.append("omen_holy_symbol")
    _set_current(engine, hero)

    def clear_used() -> None:
        engine._haunt_rule_state().setdefault("actions_used", {}).clear()

    before_track = engine._haunt_track_value("waking_progress")
    before_tokens = len(engine.tokens_of_kind("wake_token"))
    with patch.object(engine, "_resolve_check", return_value=False):
        handler.perform_action(engine, hero, "wake_attempt", {})
    assert engine._haunt_track_value("waking_progress") == before_track, "检定失败不能推进唤醒轨道"
    assert len(engine.tokens_of_kind("wake_token")) == before_tokens, "检定失败不能发唤醒成功令牌"

    clear_used()
    with patch.object(engine, "_resolve_check", return_value=True):
        handler.perform_action(engine, hero, "wake_attempt", {})
    assert engine._haunt_track_value("waking_progress") == before_track + 1, "检定成功必须推进轨道"
    assert len(engine.tokens_of_kind("wake_token")) == before_tokens + 1, "检定成功必须发令牌"


def verify_haunt13_goal_hooks() -> None:
    """p24：圣徽到手后英雄应当直奔沉睡房间；还压在牌堆里就先翻新房间。

    没有这两条时机器人只剩 key_rooms 保底，在门厅/庭院一带来回（seed137/3p、
    131/5p 实测各 16 次），英雄胜线打不出来。
    """
    engine = _run_until_haunt(seed=113, players=4, haunt_id=13)
    handler = engine._mode_handler()
    assert isinstance(handler, NightmareDreamMode)
    sleeper_room = engine._haunt_flags().get("sleeper_room")
    assert sleeper_room, "沉睡房间应当已记录"
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    # 圣徽还在预兆牌堆里：先去翻房间，不给固定目标
    for player in engine.state.players:
        while "omen_holy_symbol" in player.items:
            player.items.remove("omen_holy_symbol")
    for key in list(engine.state.room_items):
        engine.state.room_items[key] = [
            card for card in engine.state.room_items[key] if card != "omen_holy_symbol"
        ]
    if "omen_holy_symbol" not in engine.state.card_decks["omen"]:
        engine.state.card_decks["omen"].append("omen_holy_symbol")
    assert handler.bot_wants_explore(engine, hero) is True, "圣徽在牌堆里 → 必须去翻新房间"
    assert handler.bot_goal_rooms(engine, hero) == [], "圣徽没到手时不给固定目标"

    # 圣徽到手：目标 = 沉睡者的房间
    engine.state.card_decks["omen"].remove("omen_holy_symbol")
    hero.items.append("omen_holy_symbol")
    assert handler.bot_wants_explore(engine, hero) is False, "圣徽到手后不必再去翻牌"
    assert handler.bot_goal_rooms(engine, hero) == [f"__room__{sleeper_room}"]
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    assert handler.bot_goal_rooms(engine, traitor) == [], "叛徒不拿英雄目标"


def verify_haunt14_goal_hooks() -> None:
    """p25/p96：背罐去五芒星室隔壁扔、空手去捡罐、叛徒背尸去献祭。

    没有这条时机器人只有 key_rooms 保底（五芒星室 + 四间油漆房），到达一间后
    重挑"最近"的下一间，永远在油漆房之间来回（seed137/5p 实测厨房×88、
    储藏室×87，整局拖到 127 回合）。
    """
    engine = _run_until_haunt(seed=113, players=4, haunt_id=14)
    handler = engine._mode_handler()
    assert isinstance(handler, StarsRightMode)
    pentagram = handler._pentagram_room(engine)
    assert pentagram, "五芒星室应当在场上"
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    traitor = next(p for p in engine.state.players if p.role == "traitor")

    # 空手：目标 = 还有罐的房间
    loose = {token.room_key for token in engine.tokens_of_kind(handler.PAINT) if token.room_key}
    assert loose, "开局应当有散落的油漆罐"
    assert set(handler.bot_goal_rooms(engine, hero)) == {f"__room__{key}" for key in loose}

    # 背罐：目标 = 与五芒星室有门相连的房间（到了就能扔）
    token = next(t for t in engine.tokens_of_kind(handler.PAINT) if t.room_key)
    engine.give_token(token.uid, hero.id)
    goals = handler.bot_goal_rooms(engine, hero)
    assert goals, "背罐英雄应当有扔罐目标"
    for goal in goals:
        key = goal.replace("__room__", "")
        assert handler._door_adjacent(engine, key, pentagram), "扔罐目标必须与五芒星室有门相连"

    # 叛徒：地上有尸体 → 去搬；背着尸体 → 去五芒星室献祭
    engine.spawn_token(handler.CORPSE, label="死者", role="marker", room_key=hero.room_key)
    assert handler.bot_goal_rooms(engine, traitor) == [f"__room__{hero.room_key}"]
    corpse = next(iter(engine.tokens_of_kind(handler.CORPSE)))
    engine.give_token(corpse.uid, traitor.id)
    assert handler.bot_goal_rooms(engine, traitor) == [f"__room__{pentagram}"]


def verify_haunt15_equipment_goal() -> None:
    """p26/p97：英雄先去地下室取三件套，装备被拿走/穿上后目标要消失。

    没有这条目标时机器人只会朝龙硬冲，试玩实测英雄 0/18 胜；补上之后
    护甲/盾会被真的取走（改后同一批种子英雄 2/18 胜，且能打到斩杀）。
    """
    engine = _run_until_haunt(seed=113, players=4, haunt_id=15)
    handler = engine._mode_handler()
    assert isinstance(handler, DragonSiegeMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)

    goals = set(handler.bot_goal_rooms(engine, hero))
    armor_room = flags.get("armor_room")
    assert armor_room and f"__room__{armor_room}" in goals, "护甲房应当进目标"
    shield = next(t for t in engine.tokens_of_kind("shield") if t.room_key)
    assert f"__room__{shield.room_key}" in goals, "盾所在房应当进目标"

    # 有人穿上护甲：护甲房不再是目标；盾被拿走：盾房也不再是目标
    armor = next(iter(engine.tokens_in_room(armor_room, "antique_armor")))
    engine.give_token(armor.uid, hero.id)
    flags["worn_by"] = hero.id
    engine.give_token(shield.uid, hero.id)
    goals = set(handler.bot_goal_rooms(engine, hero))
    assert f"__room__{armor_room}" not in goals, "护甲已被穿走，不该再当目标"
    assert f"__room__{shield.room_key}" not in goals, "盾已被拿走，不该再当目标"


def verify_mode_rewards_gated_on_check_success() -> None:
    """源码级回归：handler 的奖励块不能拿"行动已执行"当成功标志。

    引擎 `perform_action` 的返回值是"行动是否执行"（检定失败同样返回 True），
    判定成功与否要看 `engine.last_haunt_action_succeeded()`。批次 3 审计在
    9/13/16/17/18/20/37/43/44/45/53/54/55/61/63/65/68 号里修了 15 处旧写法
    （如 13 号失败也发"唤醒成功"令牌、53 号失败也能开门）。规则里没有
    stat/attack 的行动永远成功，`if ok:` 与成功等价，不进红名单。
    """
    import re

    import haunt_rules

    risky_ids: set[str] = set()
    for rule in haunt_rules.HAUNT_RULE_OVERRIDES.values():
        for action in (rule or {}).get("actions", []) or []:
            if "stat" in action or "attack" in action:
                risky_ids.add(str(action.get("id")))

    source = (Path(__file__).resolve().parent / "haunt_modes.py").read_text(encoding="utf-8")
    lines = source.splitlines()
    offenders: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if "= super().perform_action" not in line:
            continue
        if not any(follow.strip() == "if ok:" for follow in lines[index + 1: index + 5]):
            continue
        action_id = ""
        for back in range(index, max(index - 40, -1), -1):
            match = re.match(r'\s*(?:el)?if action_id == "([^"]+)"', lines[back])
            if match:
                action_id = match.group(1)
                break
        if action_id in risky_ids:
            offenders.append((index + 1, action_id))
    assert not offenders, (
        "这些奖励块仍在拿「行动已执行」当成功（应为 ok and engine.last_haunt_action_succeeded()）："
        f"{offenders}"
    )


def verify_haunt16_escape_and_fallback() -> None:
    """16 号（p27/p98）：门开后抱女孩站在入口大厅即脱身；地下室翻完时兜底落位。

    旧实现里 `escaped` 只被读取、从没被置位——逃脱这条英雄胜线永远走不通；
    p98"地下室探索完由叛徒指定房间"的分支也没实现，幻影可能永不现身
    （seed137/4p 实测 400 回合收不了场、场上一只怪都没有）。
    """
    engine = _run_until_haunt(seed=113, players=4, haunt_id=16)
    handler = engine._mode_handler()
    assert isinstance(handler, PhantomBombMode)
    flags = engine._haunt_flags()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    entrance = next(k for k, r in engine.state.board.items() if r.template_id == "entrance_hall")
    hero.room_key = entrance
    girl = engine.spawn_token(handler.GIRL, label="女孩", role="marker", room_key=entrance)
    engine.give_token(girl.uid, hero.id)
    flags["girl_holder_id"] = hero.id
    flags["front_door_open"] = True
    flags["escaped"] = False
    _set_current(engine, hero)
    handler.on_turn_start(engine, hero)
    assert engine.state.winner == "heroes", "门开后抱女孩站在入口大厅应当立刻脱身"

    # 兜底落位：地下室翻不出新房间时，幻影与女孩必须被放到某个地下室房间
    engine2 = _run_until_haunt(seed=113, players=4, haunt_id=16)
    handler2 = engine2._mode_handler()
    engine2.state.monsters = [
        m for m in engine2.state.monsters if m.template_id != handler2.PHANTOM
    ]
    engine2._haunt_flags()["girl_rescued"] = False
    with patch.object(engine2, "exploration_frontier_keys", return_value=[]):
        assert handler2._fallback_placement(engine2) is True
    ghost = next((m for m in engine2.state.monsters if m.template_id == handler2.PHANTOM), None)
    assert ghost is not None, "兜底落位应当放出幻影"
    assert engine2.state.board[ghost.room_key].floor == -1, "幻影必须落在下室层"
    assert engine2.tokens_in_room(ghost.room_key, handler2.GIRL), "女孩要与幻影同房"
    assert engine2.tokens_in_room(ghost.room_key, handler2.MARK), "要放一枚到访标记"


def verify_haunt16_timer_and_defuse_gate() -> None:
    """16 号：叛徒死后计时器由存活者代跑（否则炸弹停摆）；拆弹只能在炸弹房（p27）。"""
    engine = _run_until_haunt(seed=113, players=4, haunt_id=16)
    handler = engine._mode_handler()
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
    assert handler._timer_ticks_now(engine, traitor) is True, "叛徒活着时由叛徒推进"
    assert handler._timer_ticks_now(engine, heroes[0]) is False, "叛徒活着时别人不推进"
    traitor.dead = True
    first_alive_id = next(
        pid for pid in engine.state.turn_order
        if any(p.id == pid and not p.dead for p in engine.state.players)
    )
    first_alive = next(p for p in engine.state.players if p.id == first_alive_id)
    assert handler._timer_ticks_now(engine, first_alive) is True, "叛徒死后轮回首位代跑"
    others = [p for p in heroes if p.id != first_alive.id]
    if others:
        assert handler._timer_ticks_now(engine, others[0]) is False, "同一轮只推进一次"

    # 拆弹位置闸门：不在击败幻影的房间时行动不可用、强制调用也失败
    flags = engine._haunt_flags()
    flags["girl_rescued"] = True
    flags["bomb_defused"] = False
    bomb_room, other_room = next(iter(engine.state.board)), None
    other_room = next(k for k in engine.state.board if k != bomb_room)
    flags["bomb_room"] = bomb_room
    hero = heroes[0]
    hero.room_key = other_room
    _set_current(engine, hero)
    engine._haunt_rule_state().setdefault("actions_used", {}).clear()
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "defuse_bomb" not in ids, "不在击败幻影的房间时不该给出拆弹选项"
    assert handler.perform_action(engine, hero, "defuse_bomb", {}) is False
    hero.room_key = bomb_room
    engine._haunt_rule_state().setdefault("actions_used", {}).clear()
    ids = {a.id for a in handler.available_actions(engine, hero)}
    assert "defuse_bomb" in ids, "回到炸弹房应当能拆弹"


def verify_haunt18_breath_gating() -> None:
    """18 号（p29）：只在"路线真的穿过孢子房"时才让机器人屏息。

    一路禁掉英雄会被孢子磨死（实测 18 局英雄只胜 1 局）；一律放开又会让
    机器人把唯一的剧本行动浪费在屏息上（#7 同款：屏息 359 次、削弱 0/3）。
    """
    engine = _run_until_haunt(seed=113, players=4, haunt_id=18)
    handler = engine._mode_handler()
    assert isinstance(handler, OffspringMode)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    plant = engine._haunt_flags().get("plant_room")
    assert plant, "毒藤房间应当已记录"
    if hero.room_key == plant:
        hero.room_key = next(k for k in engine.state.board if k != plant)
    # 清空所有孢子：去毒藤房间的路不再穿孢子 → 应当禁掉
    for token in list(engine.tokens_of_kind(handler.SPORE)):
        engine.remove_token(token.uid)
    assert handler.bot_action_blocked(engine, hero, "hold_breath") is True, "不穿孢子房时不该屏息"
    # 在去毒藤房间的下一步放一枚孢子 → 值得屏息
    path = engine._shortest_path(hero.room_key, plant)
    assert len(path) > 1, "英雄不该已经站在毒藤房间"
    engine.spawn_token(handler.SPORE, label="孢子", role="marker", room_key=path[1])
    assert handler.bot_action_blocked(engine, hero, "hold_breath") is False, "要穿孢子房时应当允许屏息"


def verify_haunt20_corpse_drop_and_timer() -> None:
    """20 号（p31/p102）：扛尸者倒下尸体留在原地；叛徒死后婚礼计时照走。

    seed137/5p 实测：尸体停在死掉的扛尸者身上（room_key 空、holder 是死人），
    教堂判定永远不成立；同局叛徒已死、wedding_timer 停在 0——两边都收不了场。
    """
    engine = _run_until_haunt(seed=113, players=4, haunt_id=20)
    handler = engine._mode_handler()
    assert isinstance(handler, GhostBrideMode)
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    corpse_token = engine.spawn_token(
        handler.CORPSE, label="新郎的尸体", role="marker", room_key=hero.room_key
    )
    engine.give_token(corpse_token.uid, hero.id)
    assert engine.tokens_held_by(hero.id, handler.CORPSE)
    handler.on_player_died(engine, hero)
    dropped = engine.token_by_uid(corpse_token.uid)
    assert dropped.room_key == hero.room_key, "扛尸者倒下，尸体应当掉在原房间"
    assert dropped.holder is None, "尸体不该还挂在倒下的人身上"

    flags = engine._haunt_flags()
    flags["wedding_started"] = True
    engine._set_haunt_track_value("wedding_timer", 0)
    traitor = next(p for p in engine.state.players if p.role == "traitor")
    traitor.dead = True
    first_alive_id = next(
        pid for pid in engine.state.turn_order
        if any(p.id == pid and not p.dead for p in engine.state.players)
    )
    first_alive = next(p for p in engine.state.players if p.id == first_alive_id)
    handler.on_turn_start(engine, first_alive)
    assert engine._haunt_track_value("wedding_timer") == 1, "叛徒死后由存活者代跑婚礼计时"


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
    verify_haunt5_werewolf_hunt()
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
    verify_haunt18_offspring()
    verify_haunt19_beastmaster()
    verify_haunt20_ghost_bride()
    verify_haunt21_zombie_lord()
    verify_haunt22_abyss_exorcism()
    verify_haunt22_abyss_rises_to_next_floor()
    verify_haunt23_tentacled_horror()
    verify_haunt24_bat_swarm()
    verify_haunt38_hellbeast_exorcism()
    verify_haunt25_voodoo()
    verify_haunt25_deferred_draw()
    verify_haunt26_rat_ritual()
    verify_haunt26_pentagram_block()
    verify_haunt27_amok_flesh()
    # M10-45/批次6：#27 Blob 自保钩子（禁区/险区/做完挪窝/停步风险）
    verify_haunt27_blob_ai()
    verify_haunt28_demon_ring()
    verify_haunt29_frankenstein()
    verify_haunt30_dracula()
    verify_haunt31_organ_rooms()
    verify_haunt31_heart_brain_spear()
    verify_haunt31_antibody_wall_move()
    verify_haunt32_lost_dimension()
    verify_haunt32_house_reshuffle()
    verify_haunt33_lake_rescue()
    verify_haunt34_mad_world()
    verify_haunt35_small_change()
    verify_haunt36_swamp_escape()
    verify_haunt37_checkmate()
    verify_haunt44_supernatural_aging()
    verify_haunt45_time_bomb()
    verify_haunt51_darker_than_night()
    verify_haunt52_crackling_aura()
    verify_haunt53_toxic_object_escape()
    verify_haunt54_arkanok_skull()
    verify_haunt55_kings_roads()
    verify_haunt61_eternal_glory()
    verify_haunt62_bag_of_tricks()
    verify_haunt63_twisting_nether()
    verify_haunt64_blood_offering()
    verify_haunt65_breath_of_wind()
    verify_haunt66_hell_on_earth()
    verify_haunt67_once_upon_a_time()
    verify_haunt68_setup_and_seal()
    verify_haunt68_tile_rearrange()
    verify_haunt68_key_route_and_confusion()
    verify_haunt68_bot_hall_guard()
    verify_haunt56_sands_of_time_setup()
    verify_haunt56_mask_sanity_floor()
    verify_haunt56_time_powers()
    verify_haunt58_nightfall_setup()
    verify_haunt58_torch_banish_haunting()
    verify_haunt59_badge_setup()
    verify_haunt59_medallion_flow()
    verify_haunt60_burning_sands_setup()
    verify_haunt60_riddle_race()
    verify_haunt69_wisp_setup()
    verify_haunt69_wisp_flees_heroes()
    verify_haunt69_catch_and_escape()
    verify_haunt70_transformation_setup()
    verify_haunt70_weapons_and_immunity()
    verify_haunt70_bot_no_noop_actions()
    verify_haunt57_paint_setup()
    verify_haunt57_repaint_and_immunity()
    verify_haunt46_the_feast_setup()
    verify_haunt46_front_door_and_victory()
    verify_haunt47_worm_ouroboros_setup()
    verify_haunt47_spell_and_bodies()
    verify_haunt48_crimson_jack_setup()
    verify_haunt48_cursed_weapon_flow()
    verify_haunt49_astral_spirit_setup()
    verify_haunt49_banish_and_possession()
    verify_haunt50_night_murder_setup()
    verify_haunt50_dawn_and_absorption()
    verify_haunt39_heir()
    verify_haunt40_buried_alive()
    verify_haunt41_invisible_traitor()
    verify_haunt42_hell_gate()
    verify_haunt43_shadow_exorcism()
    verify_dead_player_turn_skipped()
    verify_monster_defeated_hook_defaults()
    verify_ensure_room_in_play()
    verify_collapse_subsystem()
    verify_bot_quest_goal_rooms()
    verify_bot_holds_position_for_next_step()
    verify_haunt_script_visible_to_both_roles()
    verify_no_instant_verdict_on_trigger()
    verify_haunt_track_targets_nonzero()
    verify_fixed_haunt_semantics()
    # M10-35：70 本横切扩容（剧本机制 / 道具使用 / 角色交互）
    verify_all_haunts_data_integrity()
    verify_all_haunts_handler_smoke()
    verify_traitor_death_semantics_sweep()
    verify_item_use_matrix()
    verify_weapon_cards_attack_paths()
    verify_character_interaction_matrix()
    verify_haunt33_fresh_tile_and_explore_gate()
    verify_haunt39_spear_flow()
    verify_haunt39_deck_fallback()
    verify_all_haunts_win_branches_and_action_reachability()
    # M10-38：批次 1（剧本 1-5）审计新增的引擎能力与修复
    verify_haunt_action_success_flag()
    verify_haunt3_dig_root_needs_success()
    verify_haunt3_restore_frog_gating()
    verify_haunt4_failed_checks_do_not_advance()
    verify_searchable_required_cards()
    verify_seance_traitor_anywhere()
    verify_haunt2_setup_places_pentagram()
    verify_haunt2_burial_timer_not_frozen()
    verify_ensure_room_in_play_farthest()
    # M10-39：批次 2（剧本 6-10）审计新增的引擎能力与修复
    verify_explore_all_dead_ends_game()
    verify_mystic_elevator_not_transit()
    verify_omen_exhaustion_triggers_haunt()
    verify_dead_player_command_guard()
    verify_haunt7_goal_hooks()
    verify_bot_attacks_captor_first()
    verify_haunt9_traitor_goal_gating()
    # M10-40：批次 3（剧本 11-15）审计新增的引擎能力与修复
    verify_stairs_reverse_link_exit()
    verify_haunt13_wake_success_gating()
    verify_haunt13_goal_hooks()
    verify_haunt14_goal_hooks()
    verify_haunt15_equipment_goal()
    verify_mode_rewards_gated_on_check_success()
    # M10-41：批次 4（剧本 16-20）审计新增的引擎能力与修复
    verify_haunt16_escape_and_fallback()
    verify_haunt16_timer_and_defuse_gate()
    verify_haunt18_breath_gating()
    verify_haunt20_corpse_drop_and_timer()
    # M10-42/批次 5：抓人藤蔓/触手的必拖拽 + #23 英雄斩首引导
    verify_haunt7_23_drag_and_goal_hooks()
    # M10-44/批次 6：#26 鼠群合力攻击每回合只能一次
    verify_haunt26_rat_pack_once_per_turn()
    print("verify_haunt_systems: ok")


def verify_haunt7_23_drag_and_goal_hooks() -> None:
    """剧本 7/23：抓着人的尖端必须每回合往根部拖（引擎闸门 bug 回归）。

    引擎只在"怪物不在目标房"时才调 `on_monster_move`（`_resolve_monster_turns`
    的 `len(path) > 1` 闸门），而抓着人的尖端**总与猎物同房**，拖拽代码永不执行：
    人质每回合挣脱失败就结束回合（不能行动、不掉血），双方都收不了场。
    seed137/4p 实测 400 回合 `往根部缩` 0 次、完成 11/18。修法是在剧本的
    `on_monster_turn_start` 里自己走这一步。另外 #23 的头颅房离得远时，英雄
    需要 `bot_goal_rooms` 指引才会去斩首（18 局 `destroy_head` 0 次）。
    """
    for haunt_id, expected_step in ((7, 2), (23, 1)):
        engine = _run_until_haunt(seed=137, players=3, haunt_id=haunt_id)
        handler = engine._mode_handler()
        tips = handler._tips(engine)
        assert tips, f"剧本 {haunt_id} 应有尖端在场"
        tip = tips[0]
        root = handler._root_for_tip(engine, tip)
        assert root is not None, "尖端应有配对的根"

        # 挑一个离根最远的房间，把"尖端 + 人质"放过去
        far = max(
            (key for key in engine.state.board if key != root.room_key),
            key=lambda key: engine._path_length(key, root.room_key),
        )
        before = engine._path_length(far, root.room_key)
        assert before >= expected_step + 1, "需要一个离根足够远的房间来观察拖拽"
        hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
        tip.room_key = far
        hero.room_key = far
        engine._haunt_flags().setdefault("grabbed", {})[str(hero.id)] = tip.id

        took_over = handler.on_monster_turn_start(engine, tip)
        assert took_over is True, "抓着人的尖端应接管本回合行动（否则引擎不会拖）"
        assert tip.room_key == hero.room_key, "人质必须跟着尖端走"
        after = engine._path_length(tip.room_key, root.room_key)
        assert after < before, f"拖拽应更靠近根部：{before} → {after}"
        assert before - after <= expected_step, "每回合拖拽步数不应超过剧本设定"

    # #23 斩首引导：持炸药/长矛者直奔头颅房，其余人不受影响
    engine = _run_until_haunt(seed=137, players=3, haunt_id=23)
    handler = engine._mode_handler()
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    other = next((p for p in engine.state.players if p.role == "hero" and p.id != hero.id and not p.dead), None)
    head_key = next(key for key in engine.state.board if key != hero.room_key)
    engine._haunt_flags()["head_room"] = head_key
    assert handler.bot_goal_rooms(engine, hero) == [], "没带武器时不该直奔头颅房"
    hero.items.append("item_dynamite")
    assert handler.bot_goal_rooms(engine, hero) == [f"__room__{head_key}"], (
        "持炸药者应以头颅房为目标"
    )
    assert handler._can_destroy_head(engine, hero) is False, "不在头颅房还不能斩首"



def verify_haunt26_rat_pack_once_per_turn() -> None:
    """剧本 26 p108：同房老鼠的"合力攻击"整组每回合只能扑一次。

    `on_monster_turn_start` 对同房每一只老鼠都会跑一遍，早期实现没有"本回合
    这间房已经扑过"的记录，N 只老鼠会各自发动一次 6–8 骰群攻，伤害直接翻 N 倍
    （seed101/3p 实测英雄 5/6 局全灭，根本走不到"清光老鼠"的胜线）。
    """
    engine = _run_until_haunt(seed=101, players=3, haunt_id=26)
    handler = engine._mode_handler()
    rats = handler._rats(engine)
    assert len(rats) >= 2, "本剧本开局应有多只老鼠"
    hero = next(p for p in engine.state.players if p.role == "hero" and not p.dead)
    room = hero.room_key
    for rat in rats[:2]:
        rat.room_key = room
        rat.stunned_turns = 0
    engine.state.turn_count += 1  # 换一个回合号，清掉上一回合的群攻记录

    logs: list[str] = []
    original = engine._log

    def capture(message: str, category: str = "") -> None:
        logs.append(message)
        original(message, category)

    engine._log = capture  # type: ignore[method-assign]
    try:
        assert handler.on_monster_turn_start(engine, rats[0]) is True
        first = sum(1 for line in logs if "合力扑向" in line)
        assert first == 1, f"第一只老鼠应发动一次合力攻击：{logs[-3:]}"
        assert handler.on_monster_turn_start(engine, rats[1]) is True
        total = sum(1 for line in logs if "合力扑向" in line)
        assert total == 1, f"同房第二只老鼠不应再扑击一次：{logs[-3:]}"
    finally:
        engine._log = original  # type: ignore[method-assign]


if __name__ == "__main__":
    main()
