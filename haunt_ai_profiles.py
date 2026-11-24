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
            # p15：目标随"网破没破、卵毁没毁、门开没开"推进，不能写进静态
            # target_rooms——静态表（+130）会压过剧本动态目标（+95），实测
            # 英雄全挤在入口大厅来回踱步、毁卵行动 used=0。前门目标由
            # open_front_door.rooms 走通用换算，去蛛网房由 WebEscapeMode
            # .bot_goal_rooms 动态给出（同 68 号钥匙房口径）。
            "target_rooms": [],
            # 巨型蜘蛛按 Turn Traits 表长到 Might 7-8，而胜利清单里没有
            # "杀死蜘蛛"——与它互殴只会把英雄耗死在倒计时结束前（实测
            # 44 局全部死于蜘蛛或孵化）。躲着走清单才是人的打法。
            "attack_monsters": False,
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
            # 目标房间（研究实验室/厨房）不写死：只有持书的人去才做得出喷雾，
            # 写死会让全体英雄往实验室挤。书还没进场时由 CarnivorousIvyMode
            # 的 bot_wants_explore 接管（去翻新房间找书），持书后目的地由
            # make_plant_spray 行动的 rooms 提供（bot_action_blocked 已把
            # 非持有人挡在门外）。
            "target_rooms": [],
            # 不追爬行物：杀尖端只是击晕、不解决问题，追过去反而被反击抓走
            # 拖向根部吞噬（68 号同款坑）。同房间自己挨打时照常还手（
            # _filter_attack_targets 不看这一项），拿喷雾后由
            # CarnivorousIvyMode.bot_goal_rooms 指向有根/尖端的房间。
            "attack_monsters": False,
            "protect_humans": True,
            "victory_focus": "带书制作植物喷雾，然后逐个清理爬行物",
        },
        "traitor": {
            "objective_type": "destroy_key_item",
            "needed_items": ["植物喷雾"],
            # 同上：销毁房间只在抢到喷雾后才算目标，由 destroy_spray 行动的
            # rooms 提供，bot_action_blocked / bot_goal_suppressed 把关。
            "target_rooms": [],
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
            # 销毁房间（深渊/熔炉房/地下湖）不写死：圣徽不在手上时这些房间
            # 不是目的地，写死会让叛徒来回巡视空房（seed109/3p 实测在地下室
            # 三间房之间绕了 33 圈、整局拖到 133 回合）。目标改由
            # destroy_holy_symbol 行动的 rooms 提供，DeathDanceMode 的
            # bot_action_blocked 负责"没持徽就不算目标"。
            "target_rooms": [],
            "attack_heroes": True,
            "prefer_weak_targets": False,
            "victory_focus": "夺取圣徽并带到可销毁的房间",
        },
        "scenario": {"tokens": ["黑暗提琴手", "圣徽"], "special_rules": ["delayed_traitor", "relic_objective"]},
    },
    10: {
        "hero": {
            # 目标链：陷阱房是**唯一**推进点（zombies_trapped 满人数即胜），
            # 已由 target_rooms 钉住 6 间。僵尸力量 6、疯子力量 5，英雄打不动，
            # 只能靠站进陷阱房把追人的僵尸引进来（on_monster_move 落位即判）。
            # 抽样（seed3/101 × 3/5p）单局最多困住 2 只、4/4 局英雄全灭：
            # 缺的是"顶着威胁留在陷阱房当饵"的行为，档案层没有对应开关，
            # 已在 T-03 清单里登记为需要新增 bot 能力。
            "objective_type": "lure_and_trap",
            "needed_items": [],
            "target_rooms": ["master_bedroom", "chapel", "conservatory", "game_room", "library", "attic"],
            "attack_monsters": False,
            # 叛徒开局即被疯子杀死（p92，setup 里 traitor.dead=True）。
            "attack_traitor_players": False,
            "protect_humans": True,
            "victory_focus": "站进尚未用过的陷阱房把僵尸引进来；别和它们对拼，击晕不算赢",
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
    19: {
        # 19 号（驯兽师）：英雄胜线 = 对驯兽师赢出 3 点以上（diff > 2）夺矛；
        # 默认画像 attack_traitor_players=False 让英雄永远不攻击叛徒玩家，
        # 这条胜线在 AI 层就是断的（试玩 18 局英雄 0 胜、长矛从未易手）。
        # 引擎的 special_steal 会把 diff > 2 的攻击转成"夺矛"而非伤害，
        # 只有赢 1–2 点的窄带才会真掉血，所以主动攻击的净收益为正。
        "hero": {
            "objective_type": "disarm_traitor",
            "attack_monsters": True,
            "attack_traitor_players": True,
            "protect_humans": True,
            "needed_items": ["戒指"],
            # 目标链断点：胜线要求**主动贴到驯兽师身上**并赢出 3 点以上，
            # 但档案只能表达"同房间时允许攻击"，没有任何"追叛徒玩家"的寻路目标
            # （bot 的常驻目标只有怪物房与剧本房）。抽样 4 局随从最多被击毙 3 只、
            # 英雄 4/4 全灭，长矛一次都没易手——已在 T-03 清单登记所需能力。
            "target_rooms": [],
            "victory_focus": "追着驯兽师打，赢出 3 点以上夺下长矛（别打死他）",
        },
        "traitor": {
            "objective_type": "hunt_heroes",
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "靠动物随从围杀英雄，别让任何人近身夺矛",
        },
        "monster": {"mode": "nearest_hero"},
    },
    24: {
        "hero": {
            # p35：英雄真实胜利 = 把蝙蝠封回窗外（bats_sealed 且场上无蝙蝠），
            # 不是逃生。bot 的推进点由 handler.bot_goal_rooms 动态给管风琴房，
            # 这里只兜底把管风琴房列为目标房间，并保留避开高危房间的习惯。
            "objective_type": "exorcise_seal",
            "target_rooms": ["organ_room"],
            "avoid_rooms": ["深渊", "坍塌的房间", "血房间"],
            "attack_monsters": True,
            "protect_humans": True,
            "victory_focus": "去管风琴房启动并奏响驱蝠之音，封死入口后清掉贴附的蝙蝠",
        },
        "traitor": {
            # 叛徒开局即死，traitor bot 不参与（吸收兜底），保留攻击意图无害。
            "objective_type": "block_escape",
            "target_rooms": [],
            "attack_heroes": True,
            "victory_focus": "叛徒已死，bot 不行动",
        },
        "scenario": {"special_rules": ["exorcise_seal"]},
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
            # p37：英雄两条胜线——清光老鼠，或在叛徒进五芒星室前杀死他。
            # 规则里叛徒只有一条推进点：五芒星室（perform_ritual 带 rooms）。
            # 原来 target_rooms 为空、rule_data.key_rooms 也为空，英雄侧又没有
            # 带 rooms 的行动，bot 在作祟阶段**没有任何地点目标**（抽样 4 局
            # 仪式先完成 2 局）；把五芒星室钉成目标，等于"守在他必经之处"。
            "objective_type": "kill_monsters",
            "needed_items": [],
            "target_rooms": ["pentagram_chamber"],
            "attack_monsters": True,
            "attack_traitor_players": True,
            "victory_focus": "守到五芒星室：叛徒一进门就围攻；他若不来就清老鼠阻断仪式",
        },
        "traitor": {
            "objective_type": "ritual_race",
            "needed_items": [],
            # 不动叛徒的目标表：perform_ritual 自带 rooms，已经有 +125 的目标分。
            "target_rooms": [],
            "attack_heroes": True,
            "victory_focus": "尽快赶到五芒星室完成 5 次仪式理智 3+，途中顺手杀人",
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
            # 目标链：light_torch 四间火房（自有 rooms）+ push_monster 的塔楼/深渊，
            # 由 _haunt_goal_targets 换算；静态表再有 key_rooms 会重复计分，留空。
            "objective_type": "craft_and_destroy",
            "needed_items": ["火把"],
            "target_rooms": [],
            "attack_monsters": False,
            # 叛徒本人（力 2-4 的普通角色）拿着刀追人时，不还手就是白送。
            # 实测（seed149/4p）：叛徒一个人用特质攻击 9–12 点把三名英雄逐个
            # 拍死，全程没人还手——画像没开这一条，`_filter_attack_targets`
            # 直接把叛徒从目标里滤掉了。
            "attack_traitor_players": True,
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
            # 不主动追吸血鬼：力 8 的德古拉近战落败吃差值反击，30 局实测
            # 英雄对吸血鬼发起 195 次攻击、其中 55 次直接把英雄打死（占英雄
            # 死亡的一半以上）。走位改由 handler 的 bot_goal_rooms 定向：
            # 只去"钉杀昏迷者"或"力量+武器打得过"的目标（见 p41 钉杀/长矛）。
            "attack_monsters": False,
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
    34: {
        "hero": {
            # p45：英雄胜 = 随从全被关（或杀）+ 叛徒被关（或杀）。默认画像的
            # `attack_traitor_players: False` 让英雄永远不出手打叛徒，而"抓
            # 叛徒"当前未实现、保险库开启此前又是死分支——三条叠加成死局
            # （seed101/4p 实测 300 回合收不了场）。放开还手，杀叛徒这条
            # 才走得通。
            "attack_traitor_players": True,
            "victory_focus": "力量攻击击败随从后抓住，扛到（已打开的）保险库关起来；再杀死叛徒",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "带着随从围攻元老院议员（英雄），别让他们把随从一个个扛走",
        },
        "scenario": {"special_rules": ["capture_and_carry", "vault_lockup"]},
    },
    41: {
        "hero": {
            # p52：英雄唯一的胜线是"叛徒死亡"，而默认画像
            # `attack_traitor_players: False` 让英雄永远不出手——配合
            # `bot_goal_rooms`（循侦测线索奔向叛徒）才追得上。
            # M10-56 实测 seed109/6p：修前英雄每回合只做"侦测叛徒"（217 次）、
            # 从不攻击，300 回合收不了场。
            "attack_monsters": False,
            "attack_traitor_players": True,
            "victory_focus": "侦测叛徒（知识 3+）锁定位置，追上并杀死 TA；打不过就分散逃命拖时间",
        },
        "traitor": {
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "利用隐形逐个偷袭落单英雄（sneak attack 无防御）",
        },
        "scenario": {"special_rules": ["invisible_traitor", "detection"]},
    },
    42: {
        "hero": {
            # p53：英雄胜线是"激活雕像 → 推着它去撞叛徒 → 削弱到可以攻击 → 击杀"。
            # `attack_traitor_players: False`（默认）让最后一步永远走不到：
            # 雕像把叛徒削到 0 之后 `attack_allowed` 已经放行，机器人却根本
            # 不把叛徒当目标。`required_cards` 同时补了四件圣物，配合
            # `bot_goal_rooms`（雕像房间）才凑得出这条链。
            "attack_monsters": False,
            "attack_traitor_players": True,
            "victory_focus": "先捡圣物给雕像激活（圣徽/斧/水晶球/古书），再推着雕像去撞叛徒削属性，最后收尾击杀",
        },
        "traitor": {
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "无敌期间杀英雄并把尸体搬到地窖/深渊/五芒星室，掷理智或知识 4+ 打开地狱门",
        },
        "scenario": {"special_rules": ["invulnerable_traitor", "animated_statue"]},
    },
    39: {
        "hero": {
            # p50：胜线是"继承人在王座上同时持有长矛与戒指"，而戒指常常整局
            # 攥在叛徒手里（6 局实测 5 局如此）。默认 `attack_traitor_players:
            # False` 让英雄被打死也不还手、更不会去夺牌——配合 handler 的
            # `bot_wants_steal`（打赢即抢回矛/戒），胜线才接得上。
            "attack_monsters": True,
            "attack_traitor_players": True,
            "victory_focus": "帮继承人凑齐长矛与戒指（叛徒手里就打赢抢回来），再护送他登上雕像走廊的王座",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "靠刺客与自己的攻击找出并杀死继承人（英雄全灭也算赢）",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"special_rules": ["hidden_assassins", "protect_heir"]},
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
    38: {
        "hero": {
            # p49：英雄胜 = 驱魔成功次数满员；火蝠不可被攻击（monster invulnerable，
            # 见 haunt_modes.py 7542 注释），追它纯浪费。bot 由 handler.bot_goal_rooms
            # 动态去仍可用的房间类驱魔来源（教堂/地窖/五芒星室/图书馆/研究实验室）。
            "objective_type": "exorcise_seal",
            "target_rooms": ["chapel", "crypt", "pentagram_chamber", "library", "research_laboratory"],
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "去驱魔来源房做驱魔检定，满员即放逐火蝠；绝不追打不可伤的火蝠",
        },
        "traitor": {
            # 叛徒存活操控火蝠，靠怪物回合灼烧英雄；不主动肉搏。
            "objective_type": "burn_heroes",
            "attack_heroes": True,
            "victory_focus": "把火蝠聚到英雄所在房间，靠灼烧磨死英雄",
        },
        "scenario": {"special_rules": ["exorcise_seal", "invulnerable_firebats"]},
    },
    52: {
        "hero": {
            # p63：英雄胜 = 破解戒指（把 Turn/Damage 轨打光，归零后佩戴者昏迷）
            # + 场上无恶魔。戒指开局就戴在叛徒手上，所以"同房"既是破解的前提，
            # 也是顺手揍它的机会（p134 叛徒只以固定 3 骰防守，但每次受伤 −1）。
            # 默认画像让英雄永远不出手打玩家，实测 seed109/6p 整局 0 次攻击：
            # 英雄只是走来走去挨附魔与沸血，戒指轨停在 4/5。
            # attack_monsters=False：本剧本的怪只有恶魔领主（Might 7，命中
            # 6-9 点物理伤害），追它等于送死——留给 handler 的 bot_goal_rooms
            # 把人引向戒指与五芒星室，恶魔过来时再就地还手。
            "objective_type": "disenchant_ring",
            "attack_monsters": False,
            "attack_traitor_players": True,
            "victory_focus": "持魔法尘与戴戒指的叛徒同房破解戒指，并驱逐恶魔领主",
        },
        "traitor": {
            # p134：叛徒不能做常规攻击（只能施法）、受伤 −1、固定 3 骰防守；
            # 主线是在五芒星室放弃整回合召唤恶魔领主，再用附魔/沸血磨死英雄。
            "objective_type": "summon_demon",
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "召唤恶魔领主，用法术与恶魔杀光英雄",
        },
        "scenario": {"special_rules": ["magic_dust", "anti_magic_field", "turn_damage_track"]},
    },
    50: {
        "hero": {
            # p61：没有别的胜利条件——活到日出即可（night_timer 10）。
            # rule_data 既无 key_rooms 也无英雄侧行动，档案也拿不到地点目标；
            # 唯一能表达的是"不追仆人"（打只晕一回合，白送反击伤害）。
            # 抽样 4 局夜晚进度最多 7/10、4/4 局英雄全灭：真正缺的是
            # "远离仆人/被追时拉开距离"的走位能力，已在 T-03 清单登记。
            "objective_type": "generic",
            "needed_items": [],
            "target_rooms": [],
            "attack_monsters": False,
            "attack_traitor_players": False,
            "protect_humans": True,
            "victory_focus": "撑到日出（夜晚进度 10）就能分遗产；仆人打只晕一回合，别去追",
        },
        "traitor": {
            "objective_type": "hunt_heroes",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "让仆人在第 10 回合之前杀光所有英雄；叛徒死了也不影响胜利",
        },
        "scenario": {"special_rules": ["survive_until_dawn", "growing_monsters"]},
    },
    53: {
        "hero": {
            # p64：英雄胜 = 半数逃出前门 或 净化死亡之物(熔炉房/地下湖)+半数存活。
            # bot 由 handler.bot_goal_rooms 动态给目标（去拿死亡之物→熔炉房/地下湖净化，
            # 或前门解锁后逃生）。这里把关键路线房兜底列上。
            "objective_type": "cleanse_or_escape",
            "target_rooms": ["furnace_room", "underground_lake", "entrance_hall"],
            "attack_monsters": True,
            "protect_humans": True,
            "victory_focus": "拿死亡之物去熔炉房/地下湖净化，或前门解锁后半数逃生",
        },
        "traitor": {
            # 叛徒靠狗带死亡之物 + 毒云磨英雄；攻击意图保留。
            "objective_type": "spread_poison",
            "attack_heroes": True,
            "victory_focus": "让狗带着死亡之物游荡扩散毒云，拖死英雄",
        },
        "scenario": {"special_rules": ["cleanse_or_escape", "poison_cloud"]},
    },
    54: {
        "hero": {
            # p65：英雄胜 = 持颅到遗骸房净化（ritual_progress 满）。
            # 注：分析员原本建议 attack_traitor_players:True，但实测开启后英雄会
            # 放弃净化去追叛徒，ritual_progress 始终到不了满——反而 0% 惨败。
            # 故保持默认 False，靠 handler.bot_goal_rooms 把持颅英雄引去遗骸房净化，
            # 不主动追叛徒（不追也不会阻碍净化）。
            "objective_type": "ritual_then_hunt",
            "attack_monsters": True,
            "attack_traitor_players": False,
            "victory_focus": "持颅找到遗骸房净化；追叛徒会贻误净化，故不主动追，只管推进仪式",
        },
        "traitor": {
            # 叛徒靠僵尸群磨英雄；攻击意图保留。
            "objective_type": "raise_zombies",
            "attack_heroes": True,
            "victory_focus": "用僵尸群拖住英雄，阻止其净化骷髅",
        },
        "scenario": {"special_rules": ["ritual_progress", "zombie_horde"]},
    },
    55: {
        "hero": {
            # p66：英雄胜 = 驱魔数达到玩家数。影子不会被打死——打它反而让
            # 自己吃 1 骰精神伤害，所以英雄的目标只有一个：把没用过的驱魔源
            # 走一遍（handler.bot_goal_rooms 给具体房间，走国王之路更快）。
            # 默认画像"追最近的怪"权重 +130 高于剧本目标 +125：实测
            # seed127/4p 两名英雄在花园/墓地之间对撞 300 回合，进度停在 2/4。
            "objective_type": "disenchant_roads",
            "target_rooms": [
                "research_laboratory",
                "mystic_elevator",
                "chapel",
                "conservatory",
                "crypt",
            ],
            "attack_monsters": False,
            "victory_focus": "把没用过的驱魔源走一遍（实验室/电梯用知识、教堂/温室/地窖用理智），封住国王之路",
        },
        "traitor": {
            # p137：叛徒要"所有英雄被附身或死亡"，靠影子追人与自己的攻击推进。
            "objective_type": "possess_all",
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "让影子附身所有英雄（或用攻击把他们打光）",
        },
        "scenario": {"special_rules": ["kings_roads_travel", "spores", "shadow_possession"]},
    },
    56: {
        "hero": {
            # p67：英雄胜线就是杀死叛徒。默认画像不打叛徒，人永远等时之沙
            # 自己磨——但叛徒 bot 若学会少吹风，这条线会永远走不到。
            "attack_traitor_players": True,
            "victory_focus": "持戒指理智清幽影，或独处骗命运放逐；能打到叛徒就下手",
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
            # 默认追怪 +130 会压过熔炉房；没火把时 handler 也挡住打噩梦。
            "attack_monsters": False,
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
            # p70：徽章开局在叛徒手里。默认不打叛徒就永远夺不回徽章，
            # 3 人局又没有猫/熊去抢，整局卡死（批次 12 seed101/3p）。
            "attack_traitor_players": True,
            # 追女巫/使魔 +130 会压过追持徽章的叛徒；徽章不在怪手里时别去互殴。
            "attack_monsters": False,
            "victory_focus": "夺回王室徽章，护送（每回合限 2 格）到雕像房挂上去",
        },
        "traitor": {
            "attack_heroes": True,
            # 持徽章时要去塔楼/湖，追人 +130 会压过剧本目标 +125。
            "chase_heroes": False,
            "victory_focus": "自己或使魔把徽章送到塔楼或地下湖扔掉，守住雕像",
        },
        "scenario": {"special_rules": ["medallion_escort", "steal_medallion", "statue_threshold"]},
    },
    68: {
        "hero": {
            # p79：钥匙房与入口大厅都不能写进静态 target_rooms——该搜钥匙还是
            # 该往门口跑，取决于"手里有没有钥匙""门开没开"，全由
            # LabyrinthEscapeMode.bot_goal_rooms 动态给出（见 handoff §6 第 6 条）。
            "target_rooms": [],
            # 不追杀仆人：怪物房在寻路里是 +100 的常驻目标，会压过剧本动态目标（+95）。
            # 实测英雄全跑去跟仆人互殴，三把钥匙躺在地上没人捡（seed=7/5p）。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "一人拿一把钥匙带回入口大厅，凑齐后做知识 5+ 开锁，再花 2 点移动逃出去——杀死叛徒不算赢",
        },
        "traitor": {
            # p150：他捡不起也抢不走钥匙，能做的只有杀戮与拖延；迷宫自己会合上。
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "用仆人磨死英雄、拖到回合/伤害轨掷出 6+ 封闭迷宫；钥匙你碰不得",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {
            "tokens": ["钥匙", "理智检定"],
            "special_rules": ["turn_seal_roll", "confusion_force_move", "traitor_cannot_touch_keys", "escape_majority_win"],
        },
    },
    67: {
        "hero": {
            # p78：目标随已抽取任务变化，不能写进静态 target_rooms。
            # 目标链由 StorybookTwistsMode.bot_goal_rooms 按"已抽未完成任务"
            # 给出（先凑物件、再进目标房），档案层只保留"别追怪"。
            "objective_type": "collect_and_ritual",
            # 任务物件按任务不同（QUEST_ITEM_CHOICES 多选一），无法列成静态清单。
            "needed_items": [],
            "target_rooms": [],
            # p78：英雄胜线是"抽任务 → 按任务条件完成 → 活到故事结束"。
            # 打怪毫无收益，反而把自己耗死——猎蛛 Might 5 / 恶龙 Might 7，
            # 英雄低力去拼就是送人头（实测英雄 0/33 胜，全部死于怪物）。
            "attack_monsters": False,
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
            "attack_monsters": False,
            "victory_focus": "分头收集三条线索（垃圾房/游戏室/管风琴房），集齐后回作祟房解谜",
        },
        "traitor": {
            "attack_heroes": True,
            # 自己也要集线索解谜；追人 +130 会压过线索房。
            "chase_heroes": False,
            "victory_focus": "自己抢先集齐三线索回作祟房解谜（知识 5+），斯芬克斯只负责拦路",
        },
        "scenario": {"special_rules": ["riddle_race", "sphinx_toll", "clue_hunt"]},
    },
    61: {
        "hero": {
            # p72：幽灵战士与长矛都**不可被直接攻击**——英雄的唯一出路是把
            # 长矛带进遗物房做知识检定。68/69 号踩过的坑：靠搬运/集结取胜的
            # 剧本必须显式关掉 attack_monsters（+100 常驻会压过 +95 剧本目标）。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "从长矛所在房间拾矛，再把它带进两间不同的遗物房做知识检定",
        },
        "traitor": {
            "attack_heroes": True,
            "prefer_weak_targets": False,
            # 叛徒的主动胜线是"与长矛同房鼓舞幽灵 6 次"，追人 +130 会压过它。
            "chase_heroes": False,
            "victory_focus": "跟着长矛走，同房做知识/理智 6+ 攒够 6 次鼓舞",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {
            "tokens": ["命运之矛", "盾牌", "雕像", "石棺", "古代盔甲"],
            "special_rules": ["spear_control", "relic_persuasion", "inspire_race"],
        },
    },
    62: {
        "hero": {
            # p73：疯子在房间里可以被攻击——每造成 1 点物理伤害就能从他袋子里
            # 掏走一件小玩意；但他免疫远程（左轮）与炸药伤害。
            "attack_monsters": True,
            "attack_traitor_players": False,
            "victory_focus": "贴住疯子做知识 6+ 抬高轨道，再用理智检定把小玩意换成检定令牌",
        },
        "traitor": {
            # p144：疯子**不能做常规攻击**，胜利靠收集 4 件纪念品。
            "attack_heroes": False,
            "chase_heroes": False,
            "victory_focus": "在带物品符号的房间做速度 4+ 收集 4 件纪念品",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["疯子"], "special_rules": ["trinket_race", "souvenir_hunt"]},
    },
    63: {
        "hero": {
            # p74：英雄的主线是在预兆房间做知识 5+ 锚定（锚网 = 含锚房间 +
            # 与之连通的房间，门槛按人数 12/15/19/21）。虚空怪物（星界灵力量 5
            # / 幽灵理智 5 / 魅影力量 4）打不赢也不该打——实测 attack_monsters=True
            # 时英雄被贴脸后全程缠斗、整局 0/15 锚定（seed113/4p），
            # attack_monsters=False 才会边挨打边往预兆房走。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "在未锚的预兆房间做知识 5+，把房间连成锚网；没有可达的预兆房就去翻新房间",
        },
        "traitor": {
            "attack_heroes": True,
            "chase_heroes": True,
            "victory_focus": "驱使虚空怪物杀光英雄——它们能穿过虚空跨孤岛追击",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {
            "tokens": ["锚"],
            "special_rules": ["nether_decay", "anchor_race", "nether_monsters"],
        },
    },
    64: {
        "hero": {
            "attack_monsters": True,
            "attack_traitor_players": True,
            "victory_focus": "守住女孩、关掉传送门，撑到恶魔不耐烦（计时轨 7）",
        },
        "traitor": {
            "attack_heroes": True,
            "prefer_weak_targets": False,
            # 叛徒的胜线是「贴着女孩打满 5 次」，追人 +130 会压过它。
            "chase_heroes": False,
            "victory_focus": "黏住女孩用力量攻击累计 5 点伤，把她献出去",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {
            "tokens": ["女孩", "邪教徒", "蝙蝠"],
            "special_rules": ["protect_girl", "demon_timer", "portal_summon"],
        },
    },
    65: {
        "hero": {
            # p76：骚灵免疫力量，速度攻击只能抢物品、理智攻击只在持戒指/骷髅/铃铛时
            # 才降轨道——**打它拿不到任何进度**，追着它跑纯属浪费回合。英雄主线只有
            # 一条：找蜡烛 → 在作祟层点火攒知识令牌。同 63/69 号，关掉追怪。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "厨房/餐厅/小教堂/画廊找蜡烛，在作祟层点燃做知识 5+ 攒够仪式令牌",
        },
        "traitor": {
            "attack_heroes": True,
            "chase_heroes": True,
            "victory_focus": "把骚灵往杂物间/储藏室/图书馆一类房间带（回合伤害轨每回合 +1），先把英雄磨死",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {
            "tokens": ["蜡烛", "骚灵"],
            "special_rules": ["candle_hunt", "track_dice", "boost_rooms"],
        },
    },
    69: {
        "hero": {
            # p80：追上小精灵才是唯一胜利条件——打它毫无意义（它不攻击、
            # 只会跑）。68 号踩过的坑：靠追击/搬运取胜的剧本必须显式关掉
            # attack_monsters，否则 +100 常驻寻路目标压过 +95 剧本目标。
            "attack_monsters": False,
            "victory_focus": "一路追着那团光跑，追上就做知识 4+ 捕捉（别停下来打它）",
        },
        "traitor": {
            "attack_heroes": False,
            "victory_focus": "（叛徒已化为小精灵出局）跑满逃脱轨道 6 即胜",
        },
        "scenario": {"special_rules": ["wisp_escape", "spore_hazard", "traitor_removed"]},
    },
    70: {
        "hero": {
            # p81：叛徒几乎打不死——必须备克制武器（按形态）。但形态是秘密的，
            # bot 只能按已暴露的线索（bot 局直接读 flags）备武器。
            # 68 号教训：本剧本英雄目标是"备武器 + 打叛徒"，打怪寻路要保留，
            # 但别为打叛徒浪费回合——寻路目标由 bot_goal_rooms 提供。
            "attack_monsters": False,
            "attack_traitor_players": True,
            "victory_focus": "按叛徒暴露的线索备好克制武器（圣水武器/银弹左轮/杀虫剂），再围杀他",
        },
        "traitor": {
            # 访房间是唯一胜利路径：追英雄的常驻目标（+130）会压过剧本目标
            # （+125），导致叛徒一路追人却从不访房间。这里关掉追人（访完房间
            # 后由 bot_goal_rooms 接管指路），并关掉攻击英雄的主动意图。
            # 攻击意图保留（吸血鬼形态要靠打伤英雄吸血才能完成转变），
            # 但"追人"要关：否则 +130 的常驻目标会压过 +125 的访点目标，
            # 叛徒一路追人、从不访房间（实测 300 回合僵死）。
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "按选定形态访遍对应房间完成转变（吸血鬼还要吸一次血），访完再清场",
        },
        "scenario": {"special_rules": ["secret_form", "damage_immune", "weakness_weapons"]},
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
            # 追人 +130 会压过颜料房；真人会先抢罐再毁，而不是满屋追杀。
            "chase_heroes": False,
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
            # p47：真实胜利是把小艇扛到阳台/塔楼全员乘艇。静态教堂/图书馆
            # 会把人钉在错误房间（seed101/5p 实测钉在二楼平台 351 次）。
            # 寻路交给 SwampEscapeMode.bot_goal_rooms。
            "objective_type": "escape_with_boat",
            "needed_items": [],
            "target_rooms": [],
            "attack_monsters": False,
            "attack_traitor_players": False,
            "protect_humans": True,
            "victory_focus": "去阁楼扛起小艇，送到阳台或塔楼，等全员到齐再乘艇逃离",
        },
        "traitor": {
            "objective_type": "sink_the_house",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "拖延并打散英雄，不让他们带着小艇在阳台/塔楼会合",
        },
        "scenario": {"tokens": ["小艇"], "special_rules": ["flood", "rowboat_escape"]},
    },
    40: {
        "hero": {
            # p51：埋葬室在地下室、逐间排除，目标随"找到没有 / 挖到几格"变化——
            # 静态 target_rooms 会把人钉死，全交给 BuriedAliveMode.bot_goal_rooms
            # 动态给出（见 handoff §6 第 6 条）。
            # 目标链本身可执行（h40_search → h40_dig）；抽样 3 人局出现
            # "挖掘 0/3、伤害 12/12 先满"，瓶颈是力量 4+ 的成功率而不是寻路。
            "objective_type": "collect_and_ritual",
            "needed_items": [],
            "target_rooms": [],
            "attack_monsters": False,
            # 杀叛徒不算赢（p51 只认"挖出朋友"），但**必须能还手**：叛徒会
            # 主动追杀（30 局实测"全程无人还手"时 16 败 2 胜），被打死就更挖
            # 不动了。放开还手后同口径 8 败 9 胜——反击是自保，不是放弃挖土。
            "attack_traitor_players": True,
            "victory_focus": "逐间搜查地下室找到埋葬室，再轮流力量 4+ 挖掘；被叛徒缠上时先还手自保——杀死叛徒不算赢",
        },
        "traitor": {
            "attack_heroes": True,
            "victory_focus": "拖时间：每回合结束被埋者都会多挨一次伤害，别让英雄安心挖土",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["活埋伤害", "挖出朋友"], "special_rules": ["hidden_room", "dig_timer"]},
    },
    # ---------------------------------------------------------------- 补齐轮
    # 下面 19 本原先走 DEFAULT_HAUNT_AI_PROFILE（覆盖 51/70）。每条的
    # objective_type / needed_items / target_rooms 都从 haunt_rules.py 里该剧本
    # 的 actions、setup.tracks、key_rooms、required_cards 推导，victory_focus
    # 直接用 hero_goal / traitor_goal 与轨道目标改写，不套别的剧本模板。
    # 生效字段仍只有 target_rooms / avoid_rooms / attack_monsters /
    # attack_traitor_players / chase_heroes / prefer_weak_targets /
    # protect_humans——其余字段是给人和测试读的声明。
    11: {
        "hero": {
            # 英雄侧 9 条行动各自带 rooms（教堂/地窖/五芒星室/图书馆/实验室）
            # 或 requires（圣徽/戒指/古书/水晶球），目标由 _haunt_goal_targets 换算，
            # 再塞静态 target_rooms 只会重复计分，故留空。
            "objective_type": "multi_source_ritual",
            "needed_items": ["圣徽", "戒指", "古书", "水晶球"],
            "target_rooms": [],
            # 雾中人影 immune_to ["might","speed"]：只有理智攻击（持戒）能放逐，
            # 追怪前先过 attack_would_be_allowed 的可伤害闸门，所以放开不会白跑。
            "attack_monsters": True,
            "attack_traitor_players": False,
            "victory_focus": "用教堂/地窖/五芒星室/图书馆/实验室各一次驱魔，或借四件预兆各一次，凑满人数次放逐",
        },
        "traitor": {
            "objective_type": "summon_demon",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "让疯子开窗把雾中人影放进屋，靠数量优势杀光英雄",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["雾中人影", "疯子"], "special_rules": ["exorcism_sources", "window_invasion"]},
    },
    13: {
        "hero": {
            "objective_type": "collect_and_ritual",
            "needed_items": ["圣徽"],
            # 唤醒房间是"沉睡者所在房间"，由 NightmareDreamMode.bot_goal_rooms 动态给。
            "target_rooms": [],
            # p95：梦魇被击败会立刻在沉睡房间补一只（on_monster_defeated），
            # 追打零收益，还会把英雄从唤醒链上拖走。
            "attack_monsters": False,
            # 沉睡者不能被打（attack_allowed 直接拒），打了只会浪费回合。
            "attack_traitor_players": False,
            "victory_focus": "把圣徽送进沉睡者房间，凑满人数次 5+ 唤醒；别追梦魇——打死会立刻补一只",
        },
        "traitor": {
            # 叛徒开局沉睡，胜负是"逃出数 vs 逃脱房间数"的竞速（flags.escapes /
            # escape_total），没有对应枚举，用 ritual_race 表示这条计数竞速。
            "objective_type": "ritual_race",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": False,
            "chase_heroes": False,
            "victory_focus": "梦魇逃满作祟时记下的逃脱房间数即胜；每逃走一只就从沉睡房间补一只",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["梦魇", "唤醒令牌"], "special_rules": ["escape_race", "sleeping_traitor"]},
    },
    14: {
        "hero": {
            "objective_type": "collect_and_ritual",
            "needed_items": ["油漆罐"],
            # take_paint / throw_paint 没有 rooms 字段，目标回落到 key_rooms
            # （五芒星室 + 五个油漆房）。静态表会与 key_rooms 重复计分，留空。
            "target_rooms": [],
            # 杀狂信徒不推进 desecration，英雄赢线只有扔罐子。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "抢一罐油漆送到五芒星室丢进法阵，凑满人数罐；别把回合花在打狂信徒上",
        },
        "traitor": {
            "objective_type": "summon_demon",
            "needed_items": ["尸体"],
            "target_rooms": ["pentagram_chamber"],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "背尸体在五芒星室献祭凑 13 分召唤邪神；凑不满就杀光英雄",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["油漆罐", "狂信徒", "尸体"], "special_rules": ["paint_desecration", "sacrifice_points"]},
    },
    15: {
        "hero": {
            "objective_type": "hunt_with_required_item",
            "needed_items": ["古董护甲", "盾", "长矛"],
            # don_armor / take_shield 没有 rooms，目标回落到 key_rooms（地下室五间）。
            "target_rooms": [],
            # 巨龙是唯一赢线（dragon_damage 攒满人数），必须允许追它。
            "attack_monsters": True,
            # 杀叛徒不判胜，追人只会离开地下室。
            "attack_traitor_players": False,
            "victory_focus": "在地下室集齐护甲/盾/矛，把巨龙的伤害攒满人数再斩杀",
        },
        "traitor": {
            "objective_type": "burn_heroes",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "驱使巨龙烧死咬死所有英雄；自己别离开巨龙太远",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["巨龙", "古董护甲", "盾"], "special_rules": ["dragon_damage", "fire_immunity"]},
    },
    16: {
        "hero": {
            "objective_type": "rescue_then_escape",
            "needed_items": ["女孩"],
            # defuse_bomb 没有 rooms（在击败幻影的房间拆），open_front_door 是门厅；
            # 具体房间由 key_rooms + 行动换算给出。
            "target_rooms": [],
            "attack_monsters": True,
            "attack_traitor_players": False,
            "victory_focus": "在地下室击败幻影救出女孩，再拆弹（知识 7+）或开前门带她逃出",
        },
        "traitor": {
            "objective_type": "protect_countdown",
            "needed_items": [],
            "target_rooms": ["catacombs", "crypt", "furnace_room"],
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "护住炸弹拖到 20 格，或让幻影与梦魇耗死英雄",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["幻影", "女孩", "幻影印记"], "special_rules": ["bomb_timer", "rescue_escape"]},
    },
    17: {
        "hero": {
            "objective_type": "craft_and_destroy",
            "needed_items": ["配料", "杀虫剂"],
            # make_spray 自带 rooms（实验室/厨房），配料散落各房，静态表无从下手。
            "target_rooms": [],
            "attack_monsters": True,
            "attack_traitor_players": False,
            "victory_focus": "集齐三枚配料在实验室/厨房调出杀虫剂，再用速度攻击毒杀 3 只巨虫",
        },
        "traitor": {
            "objective_type": "destroy_key_item",
            "needed_items": ["配料"],
            "target_rooms": ["chasm", "furnace_room", "underground_lake"],
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "抢配料去深坑/熔炉房/地下湖销毁，毁满 4 枚即胜；毁不掉就靠虫群吃人",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["配料", "杀虫剂", "巨虫"], "special_rules": ["ingredient_race", "webbed"]},
    },
    18: {
        "hero": {
            "objective_type": "collect_cast_kill",
            "needed_items": ["花朵"],
            # find_flower 自带 rooms（温室/花园/墓地），weaken_plant 的房是毒藤所在地。
            "target_rooms": [],
            # rule_data.monsters 为空：毒藤不是怪物实体，追怪只会离开花房。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "去温室/花园/墓地找到花，带进毒藤房间做 3 次知识 5+ 削弱；孢子房要屏息",
        },
        "traitor": {
            "objective_type": "spread_poison",
            "needed_items": [],
            "target_rooms": ["conservatory", "garden", "graveyard", "chasm", "furnace_room", "underground_lake"],
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "让孢子铺满房子，把英雄毒死；别让他们把花带进毒藤房",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["毒藤", "孢子", "花朵"], "special_rules": ["spore_breath", "weaken_plant"]},
    },
    20: {
        "hero": {
            "objective_type": "collect_and_ritual",
            "needed_items": ["戒指", "新郎的尸体"],
            # 四步链的落脚点随 groom_name_known / body_disintered 变化，由
            # GhostBrideMode.bot_goal_rooms 动态给；静态表会让人停在半路。
            "target_rooms": [],
            # 新娘 invulnerable（"cannot be damaged or stunned by any means"）：
            # 默认档案追着打是纯亏，还会把新郎（持戒者）送到她嘴边。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "依次问名（卧室/餐厅/图书馆）→地窖定位→力量 4+ 掘尸→把尸体与戒指送进教堂",
        },
        "traitor": {
            "objective_type": "protect_countdown",
            "needed_items": [],
            "target_rooms": ["chapel"],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "让新娘吸干新郎的力量、把婚礼推进到第 3 回合；自己负责拦住送葬的人",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["幽灵新娘", "新郎的尸体"], "special_rules": ["wedding_timer", "groom_drain"]},
    },
    21: {
        "hero": {
            "objective_type": "hunt_with_required_item",
            "needed_items": ["徽章"],
            # 领主/徽章的位置由 ZombieLordMode.bot_goal_rooms 按"谁持徽"动态给。
            "target_rooms": [],
            # 只有持徽者能伤到领主（attack_allowed），但也必须允许清僵尸——
            # 另一条赢线是"消灭所有僵尸"。
            "attack_monsters": True,
            # 叛徒开局已死（p103），打不到任何人。
            "attack_traitor_players": False,
            "victory_focus": "护送持徽章者去打僵尸领主（只有他能造成伤害），或清光所有僵尸",
        },
        "traitor": {
            "objective_type": "raise_zombies",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "靠 6-10 只僵尸的围杀把英雄清场；叛徒开局已死，由领主代打",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["僵尸", "僵尸领主", "徽章"], "special_rules": ["medallion_required", "hero_conversion"]},
    },
    22: {
        "hero": {
            "objective_type": "multi_source_ritual",
            "needed_items": ["圣徽", "戒指", "古书", "水晶球"],
            # 英雄侧行动自带 rooms（教堂/地窖/五芒星室/图书馆/实验室），留空。
            "target_rooms": [],
            # rule_data.monsters 为空；唯一敌人是每回合塌房子的深渊。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "在五间驱魔房或借四件预兆各做一次驱魔，凑满人数次；房子每回合塌一块",
        },
        "traitor": {
            "objective_type": "sink_the_house",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "让深渊每回合吞掉一块房子，把英雄连同屋子一起埋掉",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["深渊", "驱魔令牌"], "special_rules": ["collapse_clock", "exorcism_sources"]},
    },
    23: {
        "hero": {
            "objective_type": "hunt_with_required_item",
            "needed_items": ["水晶球", "炸药", "长矛"],
            # gaze_crystal_ball / destroy_head 都没有 rooms；头颅位置由
            # handler 按 4 骰定位，静态表只会把人钉在六间 key_rooms 里。
            "target_rooms": [],
            "attack_monsters": True,
            "attack_traitor_players": False,
            "victory_focus": "持水晶球做知识 4+ 定位头颅，再带炸药或长矛进房一击摧毁",
        },
        "traitor": {
            "objective_type": "hunt_heroes",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "把英雄拖回根部，或用触手与怪物杀光他们（触手每回合成长）",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["根部", "触手尖端"], "special_rules": ["tentacle_growth", "head_hunt"]},
    },
    31: {
        "hero": {
            "objective_type": "hunt_with_required_item",
            "needed_items": ["长矛"],
            # key_rooms 有 15 间（六器官房 + 保底宝地），保底目标被稀释成
            # 15 选 1；赢线只有管风琴室（心脏）与阁楼（大脑），静态表钉死这两间。
            "target_rooms": ["organ_room", "attic"],
            # 只有长矛持有者能伤到心脏/大脑（attack_allowed），其余人追怪无效。
            "attack_monsters": True,
            # 杀叛徒不等于杀死房子（check_victory 只认 house_killed）。
            "attack_traitor_players": False,
            "victory_focus": "长矛持有者直奔管风琴室（心脏，防御力量 7）或阁楼（大脑，力量 6），赢一次攻击即杀死房子",
        },
        "traitor": {
            "objective_type": "destroy_key_item",
            "needed_items": ["长矛"],
            "target_rooms": ["chasm", "furnace_room", "underground_lake"],
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "偷走长矛，带到深渊/熔炉房/地下湖花一整回合销毁",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["心脏", "大脑", "抗体"], "special_rules": ["spear_only", "organ_rooms"]},
    },
    32: {
        "hero": {
            "objective_type": "collect_and_ritual",
            "needed_items": ["乐谱", "标本", "星象"],
            # 三条线索房与风琴房由 LostDimensionMode.bot_goal_rooms 按进度给。
            "target_rooms": [],
            # rule_data.monsters 为空；要对付的是毒大气与叛徒的干扰令牌。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "先在图书馆/游戏室/塔楼集齐 3 条线索（各 +2），再进风琴房把知识检定凑到 15-20",
        },
        "traitor": {
            "objective_type": "ritual_denial",
            "needed_items": [],
            "target_rooms": ["chapel", "game_room", "research_laboratory", "operating_laboratory", "pentagram_chamber"],
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "在五间房各放一枚干扰令牌（每枚让弹奏 -3），用毒大气拖死英雄",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["线索", "干扰令牌"], "special_rules": ["poison_atmosphere", "clue_gathering"]},
    },
    33: {
        "hero": {
            "objective_type": "rescue_then_escape",
            "needed_items": [],
            # rule_data 没有 key_rooms、没有英雄侧行动；本轮给 LakeRescueMode
            # 补了 bot_goal_rooms（返回地下湖），目标由 handler 动态给。
            "target_rooms": [],
            # 湖怪不是常驻怪物实体（handler 用 _creature_duel 结算对拼），
            # 追怪只会离开湖面。
            "attack_monsters": False,
            # 叛徒会来抢人，允许还手。
            "attack_traitor_players": True,
            "victory_focus": "全员下到地下湖、站上湖面砖搜救：4 骰 + 距离加值 + 水晶球凑 19+ 把女孩捞上来",
        },
        "traitor": {
            "objective_type": "protect_countdown",
            "needed_items": [],
            "target_rooms": ["underground_lake"],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "让溺水计时掷到 9/10 使女孩溺亡，或让湖怪吃掉所有英雄",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["湖面砖"], "special_rules": ["drown_timer", "lake_swim"]},
    },
    35: {
        "hero": {
            "objective_type": "escape_with_boat",
            "needed_items": ["玩具飞机"],
            # search_plane 自带 rooms（卧室类），escape_plane 要求站在外缘房间。
            "target_rooms": [],
            # 猫只是追兵，赢线是"半数英雄飞走"，打它不推进进度。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "在卧室类房间搜出玩具飞机、知识 4+ 发动，再从外缘房间带半数以上英雄飞走",
        },
        "traitor": {
            "objective_type": "hunt_heroes",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "让猫吃掉超过半数英雄；抓到一个就少一个能上飞机的",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["玩具飞机", "猫"], "special_rules": ["capture", "plane_escape"]},
    },
    37: {
        "hero": {
            "objective_type": "exorcise_seal",
            "needed_items": [],
            # break_seal 没有 rooms，目标回落到 key_rooms（宝库/地窖/两间实验室/游戏室）。
            "target_rooms": [],
            # 死神 invulnerable（might/sanity 全 0 且不可伤害），打它没有收益。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "在宝库/地窖/研究实验室/手术室/游戏室各破解一枚圣印（理智 4+），再在对弈中将军死神",
        },
        "traitor": {
            "objective_type": "ritual_denial",
            "needed_items": [],
            "target_rooms": ["vault", "crypt", "research_laboratory", "operating_laboratory", "game_room"],
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "让死神把英雄耗死或逼他们弃赛；守住五枚圣印不被破解",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["死神", "圣印"], "special_rules": ["seal_break", "death_chess"]},
    },
    43: {
        "hero": {
            "objective_type": "collect_and_ritual",
            "needed_items": [],
            # find_ritual / ritual_roll 自带 rooms（四间室内 + 五个外缘），留空。
            "target_rooms": [],
            # 赢线是 ritual_progress，不是杀影子；但影子会贴身打断仪式，
            # 实测把 attack_monsters 关掉反而少 1 胜（33 局 4→3），
            # 没有证据支持这条改动，保留默认 True（只在同房时出手）。
            "attack_monsters": True,
            "attack_traitor_players": False,
            "victory_focus": "先在地窖/教堂/图书馆/实验室找出光明仪式，再到外缘房间做 5+ 仪式检定，凑满人数次",
        },
        "traitor": {
            "objective_type": "hunt_heroes",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "让影子分身把英雄一个个吃掉；别让他们把仪式做完",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["影子", "仪式令牌"], "special_rules": ["ritual_find", "shadow_spawn"]},
    },
    44: {
        "hero": {
            "objective_type": "multi_source_ritual",
            "needed_items": [],
            # ritual_roll 没有 rooms，目标回落到 key_rooms（七间仪式房）。
            "target_rooms": [],
            # rule_data.monsters 为空；死亡来自每回合的衰老掷骰。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "在七间仪式房逐个做理智/知识 5+，凑满人数次复活仪式；每回合都在衰老",
        },
        "traitor": {
            "objective_type": "protect_countdown",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "靠每回合的衰老掷骰耗死英雄；别让他们把复活仪式做完",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["衰老标记", "仪式令牌"], "special_rules": ["aging_roll", "resurrection_ritual"]},
    },
    45: {
        "hero": {
            "objective_type": "disable_object",
            "needed_items": [],
            # 炸弹在玩家身上（flags.has_bomb），没有任何地点目标。
            "target_rooms": [],
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "每回合知识 7+ 拆掉自己身上的炸弹；掷出 ≤2 会引爆同房炸弹，别和队友挤在一起",
        },
        "traitor": {
            "objective_type": "protect_countdown",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "chase_heroes": False,
            "victory_focus": "等大炸弹倒计时走完 12 格，或让英雄拆弹失手引爆",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["炸弹"], "special_rules": ["bomb_defuse", "big_bomb"]},
    },
    51: {
        "hero": {
            "objective_type": "exorcise_seal",
            "needed_items": [],
            # create_seal 自带 rooms（六间镜面房），留空避免与行动重复计分。
            "target_rooms": [],
            # rule_data.monsters 为空；要防的是叛徒种的 3 枚黑暗 Hex。
            "attack_monsters": False,
            "attack_traitor_players": False,
            "victory_focus": "在六间镜面房间各做一次理智 4+ 造圣印，凑满人数枚把黑暗赶出去",
        },
        "traitor": {
            "objective_type": "hunt_heroes",
            "needed_items": [],
            "target_rooms": [],
            "attack_heroes": True,
            "prefer_weak_targets": True,
            "victory_focus": "在房子里种下 3 枚黑暗 Hex，或让分身吃光英雄",
        },
        "monster": {"mode": "nearest_hero"},
        "scenario": {"tokens": ["圣印", "黑暗 Hex"], "special_rules": ["mirror_rooms", "dark_hex"]},
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


# 合并结果的只读缓存：每回合的移动/攻击打分都会取一次 profile，而合并
# （含多层 deepcopy）与剧本无关、结果恒定，没必要每步重算。返回的是缓存
# 对象本体，调用方必须只读（当前 bot_ai 只用 .get 读值）；需要改动时自行
# deepcopy。
_PROFILE_CACHE: dict[int | None, dict[str, Any]] = {}


def get_haunt_ai_profile(haunt_id: int | None) -> dict[str, Any]:
    cached = _PROFILE_CACHE.get(haunt_id)
    if cached is None:
        if haunt_id is None:
            cached = deepcopy(DEFAULT_HAUNT_AI_PROFILE)
        else:
            cached = _deep_merge(DEFAULT_HAUNT_AI_PROFILE, HAUNT_AI_PROFILE_OVERRIDES.get(haunt_id, {}))
        _PROFILE_CACHE[haunt_id] = cached
    return cached
