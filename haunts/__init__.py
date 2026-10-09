"""按剧本拆分的 haunt mode handler 包（2026-10-06 机械拆分自 haunt_modes.py）。

新增剧本：在本包加 haunt_XX_<mode>.py（类体自带 docstring 与 mode 属性），
把模块名追加进 _MODULES 拓扑表即可——注册沿 GenericModeHandler 子类树自动完成，
兼容门面 game/haunt_modes.py 会自动再导出。
"""
from __future__ import annotations

import importlib as _importlib

from typing import Any, Protocol, runtime_checkable  # noqa: F401  原模块公开名（typing）

from .base import (  # noqa: F401
    DIRECTION_DELTAS,
    ExitOption,
    GenericModeHandler,
    HauntAction,
    HauntModeHandler,
    OPPOSITE_DOOR,
    _MODE_HANDLERS,
    _is_last_in_round,
    _monster_id,
    get_mode_handler,
    name_map,
    register_mode,
    registered_modes,
    runtime_checkable,
)

# 拓扑序：被继承的具体 handler 所在模块先导入（脚本生成）。
_MODULES = [
    "haunt_01_banishment_escort",
    "haunt_02_seance_race",
    "haunt_03_witch_and_frogs",
    "haunt_04_web_escape",
    "haunt_05_werewolf_hunt",
    "haunt_06_alien_abduction",
    "haunt_07_carnivorous_ivy",
    "haunt_08_exorcism",
    "haunt_09_delayed_traitor_relic",
    "haunt_10_trap_zombies",
    "haunt_11_spectre_exorcism",
    "haunt_12_fleshwalkers",
    "haunt_13_nightmare_escape",
    "haunt_14_paint_the_pentagram",
    "haunt_15_dragon_siege",
    "haunt_16_phantom_bomb",
    "haunt_17_bug_spray",
    "haunt_18_poisonous_plant",
    "haunt_19_beastmaster",
    "haunt_20_ghost_bride",
    "haunt_21_zombie_lord",
    "haunt_22_abyss_exorcism",
    "haunt_23_tentacled_horror",
    "haunt_24_bat_exodus",
    "haunt_25_voodoo_dolls",
    "haunt_26_rat_ritual",
    "haunt_27_blob_weakness",
    "haunt_28_demon_ring",
    "haunt_29_frankenstein_fire",
    "haunt_30_dracula_rising",
    "haunt_31_living_house",
    "haunt_32_lost_dimension",
    "haunt_33_lake_rescue",
    "haunt_34_mad_world",
    "haunt_35_small_change_escape",
    "haunt_36_swamp_escape",
    "haunt_37_death_checkmate",
    "haunt_38_hellbeast_exorcism",
    "haunt_39_secret_heir",
    "haunt_40_buried_alive",
    "haunt_41_invisible_traitor",
    "haunt_42_hell_gate_hero",
    "haunt_43_shadow_exorcism",
    "haunt_44_supernatural_aging",
    "haunt_45_time_bomb",
    "haunt_46_cannibal_feast",
    "haunt_47_worm_ouroboros",
    "haunt_48_cursed_weapon",
    "haunt_49_astral_spirit",
    "haunt_50_night_survival",
    "haunt_51_darker_than_night",
    "haunt_52_ring_exorcism",
    "haunt_53_toxic_object_escape",
    "haunt_54_arkanok_skull",
    "haunt_55_kings_roads",
    "haunt_56_time_sands",
    "haunt_57_portrait_curse",
    "haunt_58_nightfall_twilight",
    "haunt_59_badge_curse",
    "haunt_60_sphinx_riddle",
    "haunt_61_ghost_warrior",
    "haunt_62_bag_of_tricks",
    "haunt_63_twisting_nether",
    "haunt_64_blood_offering",
    "haunt_65_haunt_exorcism",
    "haunt_66_hell_on_earth",
    "haunt_67_storybook_twists",
    "haunt_68_labyrinth_escape",
    "haunt_69_wisp_capture",
    "haunt_70_inhuman_transformation",
]

for _name in _MODULES:
    _importlib.import_module(__name__ + "." + _name)


def _register_subclasses(cls) -> None:
    """沿子类树自动注册（替代原文件尾的手写注册元组，顺序不再敏感：
    _MODE_HANDLERS 以 mode 串为键）。"""
    for sub in sorted(cls.__subclasses__(), key=lambda c: c.__name__):
        if getattr(sub, "mode", None):
            register_mode(sub())
        _register_subclasses(sub)


register_mode(GenericModeHandler())  # 原注册元组的 generic 兜底
_register_subclasses(GenericModeHandler)


# 具体类名显式绑定进包命名空间（from haunts import * / 门面再导出依赖此项）。
from .haunt_01_banishment_escort import BanishmentEscortMode  # noqa: F401
from .haunt_02_seance_race import SeanceRaceMode  # noqa: F401
from .haunt_03_witch_and_frogs import WitchAndFrogsMode  # noqa: F401
from .haunt_04_web_escape import WebEscapeMode  # noqa: F401
from .haunt_05_werewolf_hunt import WerewolfHuntMode  # noqa: F401
from .haunt_06_alien_abduction import AlienAbductionMode  # noqa: F401
from .haunt_07_carnivorous_ivy import CarnivorousIvyMode  # noqa: F401
from .haunt_08_exorcism import ExorcismMode  # noqa: F401
from .haunt_09_delayed_traitor_relic import DeathDanceMode  # noqa: F401
from .haunt_10_trap_zombies import ZombieTrapMode  # noqa: F401
from .haunt_11_spectre_exorcism import SpecterInvasionMode  # noqa: F401
from .haunt_12_fleshwalkers import FleshwalkerMode  # noqa: F401
from .haunt_13_nightmare_escape import NightmareDreamMode  # noqa: F401
from .haunt_14_paint_the_pentagram import StarsRightMode  # noqa: F401
from .haunt_15_dragon_siege import DragonSiegeMode  # noqa: F401
from .haunt_16_phantom_bomb import PhantomBombMode  # noqa: F401
from .haunt_17_bug_spray import BugSprayMode  # noqa: F401
from .haunt_18_poisonous_plant import OffspringMode  # noqa: F401
from .haunt_19_beastmaster import BeastmasterMode  # noqa: F401
from .haunt_20_ghost_bride import GhostBrideMode  # noqa: F401
from .haunt_21_zombie_lord import ZombieLordMode  # noqa: F401
from .haunt_22_abyss_exorcism import AbyssExorcismMode  # noqa: F401
from .haunt_23_tentacled_horror import TentacledHorrorMode  # noqa: F401
from .haunt_24_bat_exodus import BatSwarmMode  # noqa: F401
from .haunt_25_voodoo_dolls import VoodooMode  # noqa: F401
from .haunt_26_rat_ritual import RatRitualMode  # noqa: F401
from .haunt_27_blob_weakness import AmokFleshMode  # noqa: F401
from .haunt_28_demon_ring import DemonRingMode  # noqa: F401
from .haunt_29_frankenstein_fire import FrankensteinMode  # noqa: F401
from .haunt_30_dracula_rising import DraculaRisingMode  # noqa: F401
from .haunt_31_living_house import LivingHouseMode  # noqa: F401
from .haunt_32_lost_dimension import LostDimensionMode  # noqa: F401
from .haunt_33_lake_rescue import LakeRescueMode  # noqa: F401
from .haunt_34_mad_world import MadWorldMode  # noqa: F401
from .haunt_35_small_change_escape import SmallChangeMode  # noqa: F401
from .haunt_36_swamp_escape import SwampEscapeMode  # noqa: F401
from .haunt_37_death_checkmate import DeathCheckmateMode  # noqa: F401
from .haunt_38_hellbeast_exorcism import HellbeastMode  # noqa: F401
from .haunt_39_secret_heir import HeirAssassinMode  # noqa: F401
from .haunt_40_buried_alive import BuriedAliveMode  # noqa: F401
from .haunt_41_invisible_traitor import InvisibleTraitorMode  # noqa: F401
from .haunt_42_hell_gate_hero import HellGateHeroMode  # noqa: F401
from .haunt_43_shadow_exorcism import ShadowExorcismMode  # noqa: F401
from .haunt_44_supernatural_aging import SupernaturalAgingMode  # noqa: F401
from .haunt_45_time_bomb import TimeBombMode  # noqa: F401
from .haunt_46_cannibal_feast import CannibalFeastMode  # noqa: F401
from .haunt_47_worm_ouroboros import OuroborosMode  # noqa: F401
from .haunt_48_cursed_weapon import CrimsonJackMode  # noqa: F401
from .haunt_49_astral_spirit import AstralSpiritMode  # noqa: F401
from .haunt_50_night_survival import NightMurderMode  # noqa: F401
from .haunt_51_darker_than_night import DarkerThanNightMode  # noqa: F401
from .haunt_52_ring_exorcism import CracklingAuraMode  # noqa: F401
from .haunt_53_toxic_object_escape import ToxicObjectEscapeMode  # noqa: F401
from .haunt_54_arkanok_skull import ArkanokSkullMode  # noqa: F401
from .haunt_55_kings_roads import KingsRoadsMode  # noqa: F401
from .haunt_56_time_sands import SandsOfTimeMode  # noqa: F401
from .haunt_57_portrait_curse import PortraitCurseMode  # noqa: F401
from .haunt_58_nightfall_twilight import NightfallMode  # noqa: F401
from .haunt_59_badge_curse import ForAThousandYearsMode  # noqa: F401
from .haunt_60_sphinx_riddle import BurningSandsMode  # noqa: F401
from .haunt_61_ghost_warrior import EternalGloryMode  # noqa: F401
from .haunt_62_bag_of_tricks import BagOfTricksMode  # noqa: F401
from .haunt_63_twisting_nether import TwistingNetherMode  # noqa: F401
from .haunt_64_blood_offering import BloodOfferingMode  # noqa: F401
from .haunt_65_haunt_exorcism import BreathOfWindMode  # noqa: F401
from .haunt_66_hell_on_earth import HellOnEarthMode  # noqa: F401
from .haunt_67_storybook_twists import StorybookTwistsMode  # noqa: F401
from .haunt_68_labyrinth_escape import LabyrinthEscapeMode  # noqa: F401
from .haunt_69_wisp_capture import WispCaptureMode  # noqa: F401
from .haunt_70_inhuman_transformation import InhumanTransformationMode  # noqa: F401

__all__ = [
    "AbyssExorcismMode",
    "AlienAbductionMode",
    "AmokFleshMode",
    "Any",
    "ArkanokSkullMode",
    "AstralSpiritMode",
    "BagOfTricksMode",
    "BanishmentEscortMode",
    "BatSwarmMode",
    "BeastmasterMode",
    "BloodOfferingMode",
    "BreathOfWindMode",
    "BugSprayMode",
    "BuriedAliveMode",
    "BurningSandsMode",
    "CannibalFeastMode",
    "CarnivorousIvyMode",
    "CracklingAuraMode",
    "CrimsonJackMode",
    "DIRECTION_DELTAS",
    "DarkerThanNightMode",
    "DeathCheckmateMode",
    "DeathDanceMode",
    "DemonRingMode",
    "DraculaRisingMode",
    "DragonSiegeMode",
    "EternalGloryMode",
    "ExitOption",
    "ExorcismMode",
    "FleshwalkerMode",
    "ForAThousandYearsMode",
    "FrankensteinMode",
    "GenericModeHandler",
    "GhostBrideMode",
    "HauntAction",
    "HauntModeHandler",
    "HeirAssassinMode",
    "HellGateHeroMode",
    "HellOnEarthMode",
    "HellbeastMode",
    "InhumanTransformationMode",
    "InvisibleTraitorMode",
    "KingsRoadsMode",
    "LabyrinthEscapeMode",
    "LakeRescueMode",
    "LivingHouseMode",
    "LostDimensionMode",
    "MadWorldMode",
    "NightMurderMode",
    "NightfallMode",
    "NightmareDreamMode",
    "OPPOSITE_DOOR",
    "OffspringMode",
    "OuroborosMode",
    "PhantomBombMode",
    "PortraitCurseMode",
    "Protocol",
    "RatRitualMode",
    "SandsOfTimeMode",
    "SeanceRaceMode",
    "ShadowExorcismMode",
    "SmallChangeMode",
    "SpecterInvasionMode",
    "StarsRightMode",
    "StorybookTwistsMode",
    "SupernaturalAgingMode",
    "SwampEscapeMode",
    "TentacledHorrorMode",
    "TimeBombMode",
    "ToxicObjectEscapeMode",
    "TwistingNetherMode",
    "VoodooMode",
    "WebEscapeMode",
    "WerewolfHuntMode",
    "WispCaptureMode",
    "WitchAndFrogsMode",
    "ZombieLordMode",
    "ZombieTrapMode",
    "_MODE_HANDLERS",
    "_is_last_in_round",
    "_monster_id",
    "get_mode_handler",
    "name_map",
    "register_mode",
    "registered_modes",
    "runtime_checkable",
]
