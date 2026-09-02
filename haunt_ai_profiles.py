from __future__ import annotations

from copy import deepcopy
from typing import Any


# 这个文件只给机器人使用，不会显示给玩家。
# 玩家阅读的剧本文本仍在 haunts_zh.py 和 haunts_zh/*.md。
# 后续修改机翻剧本时，不需要同步改这里；只有想调整机器人打法时才改下面的覆盖表。
DEFAULT_HAUNT_AI_PROFILE: dict[str, Any] = {
    "version": 1,
    "hero": {
        "mode": "survive_and_help",
        "objective_type": "generic",
        "target_rooms": [],
        "needed_items": [],
        "protect_items": [],
        "avoid_rooms": [],
        "prohibited_actions": [],
        "attack_monsters": True,
        "attack_traitor_players": False,
        "protect_humans": True,
        "victory_focus": "follow_hero_goal",
    },
    "traitor": {
        "mode": "hunt_heroes",
        "objective_type": "generic",
        "target_rooms": [],
        "needed_items": [],
        "protect_items": [],
        "avoid_rooms": [],
        "prohibited_actions": [],
        "attack_heroes": True,
        "prefer_weak_targets": True,
        "victory_focus": "follow_traitor_goal",
    },
    "monster": {
        "mode": "nearest_hero",
    },
    "scenario": {
        "track": None,
        "tokens": [],
        "countdown": None,
        "special_rules": [],
    },
    "notes": "通用人机策略。逐个剧本精修时，只在 HAUNT_AI_PROFILE_OVERRIDES 写覆盖项。",
}


HAUNT_AI_PROFILE_OVERRIDES: dict[int, dict[str, Any]] = {
    1: {
        "hero": {
            "objective_type": "escort_and_block",
            "needed_items": ["女孩"],
            "target_rooms": ["地下墓穴", "入口大厅", "小教堂"],
            "attack_monsters": True,
            "attack_traitor_players": False,
            "victory_focus": "保护关键同伴并阻止怪物会合",
        },
        "traitor": {
            "objective_type": "escort_monster",
            "needed_items": ["女孩"],
            "target_rooms": ["地下墓穴"],
            "prefer_weak_targets": False,
            "victory_focus": "夺取关键同伴并向怪物/目标房间靠近",
        },
        "monster": {"mode": "protect_objective"},
        "scenario": {"tokens": ["女孩", "木乃伊", "石棺"], "special_rules": ["escort"]},
    },
    2: {
        "hero": {
            "objective_type": "ritual_then_hunt",
            "needed_items": ["戒指"],
            "target_rooms": ["pentagram_chamber", "attic", "bedroom", "master_bedroom", "crypt", "graveyard"],
            "attack_monsters": True,
            "attack_traitor_players": False,
            "victory_focus": "抢先完成降灵会，随后寻找并安葬骨头或摧毁幽灵",
        },
        "traitor": {
            "objective_type": "ritual_race",
            "needed_items": ["通灵板"],
            "target_rooms": ["pentagram_chamber"],
            "attack_heroes": True,
            "prefer_weak_targets": False,
            "victory_focus": "带通灵板去五芒星室抢先召唤幽灵",
        },
        "monster": {"mode": "sanity_hunt"},
        "scenario": {"tokens": ["幽灵", "尸骨", "降灵会"], "special_rules": ["ritual_race", "delayed_monster"]},
    },
    3: {
        "hero": {
            "objective_type": "collect_cast_kill",
            "needed_items": ["书", "曼德拉草"],
            "target_rooms": ["conservatory", "larder", "kitchen", "entrance_hall"],
            "attack_monsters": True,
            "attack_traitor_players": True,
            "victory_focus": "先挖根，再带书贴近女巫施法，最后集中攻击",
        },
        "traitor": {
            "objective_type": "deny_book_and_disable",
            "needed_items": ["书"],
            "target_rooms": ["entrance_hall", "conservatory", "larder", "kitchen"],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "夺书并让女巫优先把关键英雄变成青蛙",
        },
        "monster": {"mode": "protect_caster"},
        "scenario": {"tokens": ["女巫", "青蛙", "猫", "曼德拉草"], "special_rules": ["invulnerable_until_ritual", "disable_heroes"]},
    },
    4: {
        "hero": {
            "objective_type": "rescue_then_escape",
            "needed_items": ["医疗包", "治疗药膏"],
            "target_rooms": ["entrance_hall"],
            "attack_monsters": True,
            "protect_humans": True,
            "victory_focus": "先打蛛网救揭示者，再摧毁卵并打开前门",
        },
        "traitor": {
            "objective_type": "protect_countdown",
            "needed_items": [],
            "target_rooms": ["entrance_hall"],
            "attack_heroes": True,
            "prefer_weak_targets": False,
            "victory_focus": "保护蛛卵拖到第九回合，优先拦截带医疗物品的英雄",
        },
        "monster": {"mode": "guard_trapped_hero"},
        "scenario": {"tokens": ["蛛网", "蛛卵", "巨型蜘蛛"], "special_rules": ["countdown", "escape"]},
    },
    5: {
        "hero": {
            "objective_type": "hunt_with_required_item",
            "needed_items": ["左轮手枪", "银弹"],
            "target_rooms": ["熔炉房", "研究实验室", "手术室"],
            "attack_traitor_players": True,
            "victory_focus": "寻找银弹和远程武器后围攻狼人",
        },
        "traitor": {
            "objective_type": "infect_and_hunt",
            "needed_items": [],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "优先攻击落单或低理智英雄",
        },
        "scenario": {"tokens": ["狼", "银弹"], "special_rules": ["infection"]},
    },
    6: {
        "hero": {
            "objective_type": "disable_object",
            "needed_items": [],
            "target_rooms": [],
            "attack_monsters": True,
            "attack_traitor_players": False,
            "protect_humans": True,
            "victory_focus": "分散站位，优先回到飞船房间进行力量检定",
        },
        "traitor": {
            "objective_type": "abduct_heroes",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "prefer_weak_targets": False,
            "victory_focus": "利用外星人控制英雄，沿最短路线送回飞船",
        },
        "monster": {"mode": "mind_control_then_escort"},
        "scenario": {"tokens": ["外星人", "宇宙飞船", "精神控制"], "special_rules": ["mind_control", "object_damage"]},
    },
    7: {
        "hero": {
            "objective_type": "craft_and_destroy",
            "needed_items": ["书", "植物喷雾"],
            "target_rooms": ["research_laboratory", "kitchen"],
            "attack_monsters": True,
            "protect_humans": True,
            "victory_focus": "带书制作植物喷雾，然后逐个清理爬行物",
        },
        "traitor": {
            "objective_type": "destroy_key_item",
            "needed_items": ["植物喷雾"],
            "target_rooms": ["chasm", "furnace_room", "underground_lake"],
            "attack_heroes": True,
            "prefer_weak_targets": False,
            "victory_focus": "抢走植物喷雾并把它带到危险房间销毁",
        },
        "monster": {"mode": "grab_and_return"},
        "scenario": {"tokens": ["根", "尖端", "植物喷雾"], "special_rules": ["craft_item", "grab_heroes"]},
    },
    8: {
        "hero": {
            "objective_type": "multi_source_ritual",
            "needed_items": ["圣徽", "通灵板", "书", "水晶球"],
            "target_rooms": ["chapel", "crypt", "pentagram_chamber", "library", "research_laboratory"],
            "attack_monsters": False,
            "protect_humans": True,
            "victory_focus": "分散使用不同房间和物品做驱魔检定",
        },
        "traitor": {
            "objective_type": "ritual_denial",
            "needed_items": ["通灵板"],
            "target_rooms": ["chapel", "crypt", "pentagram_chamber", "library", "research_laboratory"],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "守住驱魔来源并让女妖靠近低理智英雄",
        },
        "monster": {"mode": "wandering_wail"},
        "scenario": {"tokens": ["女妖", "驱魔"], "special_rules": ["invulnerable_monster", "multi_source_ritual"]},
    },
    9: {
        "hero": {
            "objective_type": "relic_ritual",
            "needed_items": ["圣徽"],
            "target_rooms": ["pentagram_chamber"],
            "attack_monsters": False,
            "protect_items": ["圣徽"],
            "protect_humans": True,
            "victory_focus": "护送圣徽到五芒星室并集中完成理智检定",
        },
        "traitor": {
            "objective_type": "destroy_relic",
            "needed_items": ["圣徽"],
            "target_rooms": ["chasm", "furnace_room", "underground_lake"],
            "attack_heroes": True,
            "prefer_weak_targets": False,
            "victory_focus": "夺取圣徽并带到可销毁的房间",
        },
        "scenario": {"tokens": ["黑暗提琴手", "圣徽"], "special_rules": ["delayed_traitor", "relic_objective"]},
    },
    10: {
        "hero": {
            "objective_type": "lure_and_trap",
            "needed_items": [],
            "target_rooms": ["master_bedroom", "chapel", "conservatory", "game_room", "library", "attic"],
            "attack_monsters": False,
            "protect_humans": True,
            "victory_focus": "把僵尸引进尚未用过的陷阱房间",
        },
        "traitor": {
            "objective_type": "hunt_with_zombies",
            "needed_items": [],
            "target_rooms": ["master_bedroom", "chapel", "conservatory", "game_room", "library", "attic"],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "控制僵尸封路，阻止英雄把它们带进陷阱房",
        },
        "monster": {"mode": "line_of_sight_hunt"},
        "scenario": {"tokens": ["僵尸", "疯子"], "special_rules": ["lure_monsters", "trap_rooms"]},
    },
    12: {
        "hero": {
            "objective_type": "kill_monsters",
            "attack_monsters": True,
            "protect_humans": True,
            "needed_items": ["斧头", "左轮手枪", "炸药"],
            "victory_focus": "集中火力清理怪物并保护真人",
        },
        "traitor": {
            "objective_type": "hunt_heroes",
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "与怪物夹击最弱英雄",
        },
        "monster": {"mode": "nearest_weak_hero"},
    },
    24: {
        "hero": {
            "objective_type": "escape_or_reach_room",
            "target_rooms": ["入口大厅", "门厅", "大楼梯"],
            "avoid_rooms": ["深渊", "坍塌的房间", "血房间"],
            "protect_humans": True,
            "victory_focus": "向出口和安全路线移动",
        },
        "traitor": {
            "objective_type": "block_escape",
            "target_rooms": ["入口大厅", "门厅", "大楼梯"],
            "attack_heroes": True,
            "victory_focus": "守住出口路线并拖延英雄",
        },
        "scenario": {"special_rules": ["escape"]},
    },
    36: {
        "hero": {
            "objective_type": "cooperate_and_collect",
            "needed_items": ["圣徽", "书", "铃铛", "蜡烛"],
            "target_rooms": ["小教堂", "图书馆", "研究实验室"],
            "protect_humans": True,
            "victory_focus": "抱团交换关键物品并完成检定",
        },
        "traitor": {
            "objective_type": "deny_items",
            "needed_items": ["圣徽", "书", "铃铛", "蜡烛"],
            "attack_heroes": True,
            "prefer_weak_targets": False,
            "victory_focus": "抢夺或阻止英雄使用关键物品",
        },
        "scenario": {"tokens": ["任务", "仪式"], "special_rules": ["cooperation", "item_objective"]},
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def get_haunt_ai_profile(haunt_id: int | None) -> dict[str, Any]:
    if haunt_id is None:
        return deepcopy(DEFAULT_HAUNT_AI_PROFILE)
    return _deep_merge(DEFAULT_HAUNT_AI_PROFILE, HAUNT_AI_PROFILE_OVERRIDES.get(haunt_id, {}))
