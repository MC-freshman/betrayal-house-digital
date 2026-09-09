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
    25: {
        "hero": {
            # p36 没有禁止攻击叛徒；叛徒本剧本会主动杀人凑"过半死亡"，
            # 英雄 bot 不还手就是白挨砍（实测六个种子只赢一局的主因）。
            "attack_traitor_players": True,
            "victory_focus": "搜寻并销毁自己的巫毒娃娃，必要时反击叛徒",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "在娃娃诅咒起效前把英雄杀到过半",
        },
        "scenario": {"special_rules": ["hidden_dolls", "turn_damage_track"]},
    },
    26: {
        "hero": {
            # p37：英雄胜利路径之一是"在叛徒进五芒星室前杀死他"；
            # 且老鼠会主动围攻，英雄必须反击。
            "attack_traitor_players": True,
            "victory_focus": "优先杀老鼠阻断仪式，遇到未进五芒星室的叛徒就围攻",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "尽快赶到五芒星室完成仪式，途中顺手杀人",
        },
        "scenario": {"special_rules": ["rat_swarm", "ritual"]},
    },
    27: {
        "hero": {
            # p109：叛徒会杀人或抢配料；英雄 bot 需要反击。
            "attack_traitor_players": True,
            "victory_focus": "贴着 Blob 检定弱点，再搜配料投掷，别走进有 Blob 的房间",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "阻止英雄检定与投掷，把人赶进 Blob",
        },
        "scenario": {"special_rules": ["growing_blob", "blobperson"]},
    },
    28: {
        "hero": {
            # p39：戒指开局在叛徒手里，英雄必须围攻抢戒指才能开展胜利流程。
            "attack_traitor_players": True,
            "victory_focus": "先抢戒指，再持戒指两次击败恶魔领主",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "与恶魔夹击英雄，别让他们拿到戒指",
        },
        "scenario": {"special_rules": ["hellgate", "ring_control"]},
    },
    29: {
        "hero": {
            # p40：怪物力 8 近身必死，英雄 bot 得先去点火房拿火把。
            "attack_monsters": False,
            "victory_focus": "先去点火房拿火把，再投掷烧死怪物，或引到塔楼/深渊推落",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "与怪物夹击英雄，别让他们靠近火源",
        },
        "scenario": {"special_rules": ["torch", "fire_weakness"]},
    },
    30: {
        "hero": {
            # p41：日出会削弱吸血鬼，英雄 bot 拖时间也是策略；圣徽/长矛是关键牌。
            "attack_traitor_players": True,
            "victory_focus": "躲开吸血鬼拖到日出，用长矛钉杀或把昏迷的吸血鬼钉死",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "趁夜色杀光或魅惑所有英雄，别让它们晒到太阳",
        },
        "scenario": {"special_rules": ["sunrise", "domination"]},
    },
    32: {
        "hero": {
            # p43：门槛 15+/16+/18+/20+ 远超裸掷骰上限，必须先集齐线索。
            # bot_goal_rooms 会先跑线索房再进风琴房（handler 定制寻路）。
            "attack_traitor_players": True,
            "victory_focus": "先找齐乐谱/标本/星象三条线索，再进风琴房弹对曲子",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "跑完五间房放干扰令牌，同时用毒大气和攻击拖死英雄",
        },
        "scenario": {"special_rules": ["poison_atmosphere", "clue_gathering"]},
    },
    46: {
        "hero": {
            # p57：零伤亡才能走"全员逃生"路线；bot_goal_rooms 会先追受害者再护送到门厅。
            "attack_traitor_players": True,
            "victory_focus": "先开正门，再反复护送受害者出门；一旦见血就转杀光狂徒",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "让狂徒扑杀受害者并进食变强，同时堵住英雄的护送路线",
        },
        "scenario": {"special_rules": ["victim_escort", "feasting", "front_door"]},
    },
    47: {
        "hero": {
            # p58：先捡骷髅施削弱咒（理智 5+）解锁攻击，再围殴累计重击；
            # 叛徒已变蛇出局，attack_traitor_players 无意义。
            "victory_focus": "捡起骷髅追上蛇头施咒，削弱后集中重击斩头，别让蛇身铺满 16 节",
        },
        "scenario": {"special_rules": ["weakening_spell", "body_tokens", "speed_immune"]},
    },
    48: {
        "hero": {
            # p59：前期别和杰克硬拼（打不死只会让他更强），先找武器再研究。
            "victory_focus": "先去图书馆/教堂/金库/阁楼找诅咒武器，研究满令牌后再用该武器斩杀杰克",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "让杰克缠住英雄杀光他们，别把回合浪费在别处",
        },
        "scenario": {"special_rules": ["cursed_weapon", "reviving_monster", "fear_aura"]},
    },
    49: {
        "hero": {
            # p60：攻击星界灵成功即累积驱逐令牌（不是伤害），失败也不受伤——
            # 全员贴脸输出就是最优解；灵魂不能探索，别浪费步数。
            "victory_focus": "全员围住星界灵用知识/理智轮番攻击，攒满驱逐令牌摧毁它",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "用星界灵磨掉英雄的精神属性毁掉灵魂，再让仪式附身空壳",
        },
        "scenario": {"special_rules": ["soul_out_of_body", "ritual_possession", "mental_only"]},
    },
    50: {
        "hero": {
            # p61：没有别的胜利条件——活到日出即可。仆人夜越深越强，
            # 前期能打就打，后期（8 回合后）以躲为主。
            "victory_focus": "撑到日出（夜晚进度 10）就能分遗产；后期仆人变强时优先自保",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "让仆人在第 10 回合之前杀光所有英雄；叛徒死了也不影响胜利",
        },
        "scenario": {"special_rules": ["survive_until_dawn", "growing_monsters"]},
    },
    56: {
        "hero": {
            # p67：幽影免疫力量攻击——持戒指用理智、否则去骗命运放逐；
            # 别急着围殴叛徒，逼他多用时间之力就会自毁。
            "victory_focus": "持戒指理智清幽影，或独处骗命运放逐；缠住叛徒等时之沙反噬",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "用幽影与时停磨死英雄，但每用一次时间之力都要掂量失控风险",
        },
        "scenario": {"special_rules": ["sands_of_time", "wall_phasing", "control_check"]},
    },
    58: {
        "hero": {
            # p69：暮色中不能力量/速度攻击（自动转知识攻击）；先去熔炉房点
            # 火把，再和同伴会合逐层驱散——三层清完就赢。
            "victory_focus": "先到熔炉房点起火把，再与同伴会合逐层驱散暮色（或围杀噩梦）",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "让噩梦缠住英雄啃食精神，别让他们凑齐火把与人手",
        },
        "scenario": {"special_rules": ["twilight", "torches", "haunting", "knowledge_attacks"]},
    },
    59: {
        "hero": {
            # p70：徽章开局在叛徒手里——打掉他/让猫抢了再夺回，捡到后只能
            # 慢慢挪（每回合 2 格），直奔雕像房挂上去。
            "victory_focus": "夺回王室徽章，护送（每回合限 2 格）到雕像房挂上去",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "让使魔抢走徽章送到塔楼或地下湖扔掉，守住雕像不让英雄挂徽章",
        },
        "scenario": {"special_rules": ["medallion_escort", "steal_medallion", "statue_threshold"]},
    },
    67: {
        "hero": {
            # p78：目标随已抽取任务变化，不能写进静态 target_rooms。
            "target_rooms": [],
            "attack_monsters": True,
            "attack_traitor_players": False,
            "victory_focus": "与入定叛徒同房抽任务，按任务条件完成；够数后活到故事结束",
        },
        "traitor": {
            "attack_heroes": False,
            "victory_focus": "入定读故事，用尸体令牌推悲伤结局或让怪物杀光英雄",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"special_rules": ["trance", "quests", "plot_twists", "story_track"]},
    },
    66: {
        "hero": {
            # p77：目标随圣徽位置变化，chapel/library 不能写进静态 target_rooms。
            "target_rooms": [],
            "needed_items": ["圣徽"],
            "protect_items": ["圣徽"],
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "拿到圣徽后充能、封闭房间，再在封闭房用圣徽打赢恶魔领主",
        },
        "traitor": {
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "杀掉持徽英雄；自己不能碰圣徽",
        },
        "monster": {"mode": "hunt_holy_symbol"},
        "scenario": {"special_rules": ["holy_symbol_charge", "seal_room", "banish_in_seal"]},
    },
    60: {
        "hero": {
            # p71：解谜竞速——三条线索各自收集（力量/速度/理智 4+），集齐后
            # 回作祟房知识 6+；斯芬克斯挡路每只多花 3 移动，绕开别硬闯。
            "victory_focus": "分头收集三条线索（垃圾房/游戏室/管风琴房），集齐后回作祟房解谜",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "用斯芬克斯堵住三个线索房拖慢英雄，自己抢先解谜（知识 5+）",
        },
        "scenario": {"special_rules": ["riddle_race", "sphinx_toll", "clue_hunt"]},
    },
    57: {
        "hero": {
            # p68/p139：叛徒不受伤害削减，正面围殴纯属白费——除非谁手里有
            # 远古护身符。真正的胜利只有一条：把颜料一罐罐带进画廊重绘。
            "objective_type": "collect_and_ritual",
            # 颜料房与画廊都不写在这里：画像的 target_rooms 是常驻加分（normal +100），
            # 比剧本的动态目标（normal +95）更硬，实测会把英雄钉死在"颜料早被拿走"的
            # 房间里来回踱步（seed=109/4p 重绘 0/3）。两种目标都由
            # PortraitCurseMode.bot_goal_rooms 按"手里有没有颜料"动态给出。
            "target_rooms": [],
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "一人抢一罐颜料送进画廊做知识 4+ 重绘，攒满知识检定令牌；别把回合花在打叛徒上",
        },
        "traitor": {
            # p139：毁满三罐颜料即胜，且自己绝不能进展厅（那是唯一能杀死他的地方）。
            "attack_heroes": True,
            "avoid_rooms": ["gallery"],
            "victory_focus": "抢到颜料就用它代替攻击销毁，毁满三罐即胜；离画廊越远越好",
        },
        "scenario": {
            "tokens": ["颜料", "知识检定"],
            "special_rules": ["traitor_damage_immunity", "paint_race", "portrait_gaze"],
        },
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
