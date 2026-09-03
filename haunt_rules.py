from __future__ import annotations

from copy import deepcopy
from typing import Any


# 这个文件只存程序和机器人读取的剧本规则摘要，不直接显示给玩家。
# 玩家可读文本在 haunts_zh.py 和 haunts_zh/*.md；后续润色机翻文本时不需要同步改这里。

# fidelity 标记剧本的「精修度」，让 rule_data 自己说明状态，
# 不再依赖交接文档才能判断某个剧本是否已完成严格复刻：
#   refined  = 已对照 PDF 原文逐字校准，且有专属 mode handler
#   draft    = 手写规则数据，尚未对照 PDF 校准，无专属 handler
#   skeleton = _make_scenario_rule 模板生成的骨架（11-70 号默认）
HAUNT_RULE_OVERRIDES: dict[int, dict[str, Any]] = {
    1: {
        # 校准记录（2026-08-31，对照英雄手册 p12 / 叛徒手册 p83）：
        #   已核对无误：木乃伊 Speed 3 / Might 8 / Sanity 5；两步调查均 Knowledge 6+；
        #               放逐需 2 枚知识检定令牌 + 持书与木乃伊同房间打理智战；
        #               木乃伊免疫速度攻击（左轮、炸药）。
        #   本次补齐（全部实现在 haunt_modes.BanishmentEscortMode）：
        #     · 令牌链路：石棺/木乃伊/女孩三枚令牌放置、女孩卡 set aside 与拾取、
        #       关键牌不在场时补抽（书归英雄、戒指或圣徽归叛徒）
        #     · 战斗：造成速度伤害直到对手速度触底（不降到骷髅）后转力量伤害；
        #       单次 2+ 伤害可改为夺取物品或抢走女孩（人类叛徒弹窗选，机器人自动）
        #     · 移动：掷出 0 或 1 时经秘密通道直达目标房间
        #   已知简化：秘密通道对机器人叛徒固定"追向最近英雄"，而非任选房间——
        #     原文是 "any space"，任意选择对机器人没有意义，且会破坏对局可复现。
        #     若将来要支持人类叛徒自选，在 on_monster_move 里加 prompter 询问即可。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "banishment_escort",
        "traitor_rule": "lowest_sanity",
        "hero_goal": "完成真名和咒语两步调查后，带着书在木乃伊房间用理智战斗放逐它。",
        "traitor_goal": "让木乃伊带着女孩和戒指或圣徽回到石棺房，或杀光英雄。",
        "suggested_monsters": ["mummy"],
        "required_cards": ["omen_book", "omen_girl", "omen_ring", "omen_holy_symbol"],
        "key_rooms": ["catacombs", "research_laboratory", "library", "chapel", "entrance_hall"],
        # 与 BanishmentEscortMode.setup 实际生成的令牌保持一致
        "tokens": ["sarcophagus", "mummy_marker", "girl", "knowledge_check"],
        "setup": {
            "tracks": {
                "banishment_steps": {"label": "木乃伊真名/咒语", "target": 2, "side": "heroes"},
            },
            "flags": {"girl_claimed": False, "mummy_has_girl": False},
        },
        "monsters": [
            {
                "template_id": "mummy",
                "name": "木乃伊",
                "spawn": "haunt_room",
                "speed": 3,
                "might": 8,
                "sanity": 5,
                "can_carry_items": True,
                "immune_to": ["speed_attack"],
            }
        ],
        "actions": [
            {"id": "learn_true_name", "side": "heroes", "stat": "knowledge", "target": 6, "rooms": ["catacombs", "research_laboratory", "library"]},
            {"id": "learn_spell", "side": "heroes", "stat": "knowledge", "target": 6, "requires": ["omen_book", "banishment_steps>=1"]},
            {"id": "banish_mummy", "side": "heroes", "attack": "sanity", "requires": ["omen_book", "banishment_steps>=2", "same_room:mummy"]},
        ],
        "source_pages": [12, 83],
    },
    2: {
        # 校准记录（2026-09-01，对照英雄手册 p13 / 叛徒手册 p84）：
        #   已核对无误：检定全部 5+；英雄目标 = 玩家数一半（向下取整）；
        #               幽灵 Speed 4 / Sanity 6 / 理智攻击；找骨头房间与安葬房间。
        #   本次补齐（实现在 haunt_modes.SeanceRaceMode）：
        #     · 竞速规则：叛徒须 1 次知识 + 1 次神志（不能两次同属性），持通灵板任意房间可试；
        #       英雄限五芒星室、两属性任选
        #     · 幽灵延迟生成与控制权（英雄先成 → 停在最后一次成功检定的房间）
        #     · 安葬 5 回合计时器，逾期叛徒夺控、安葬失效
        #     · 幽灵理智攻击造成精神伤害；可穿墙移动（按曼哈顿距离）
        #     · 英雄控灵期间幽灵不动不攻击（p13 "It stays there"）
        #   胜利条件修正：杀叛徒【不】算英雄胜（p84 "If the traitor dies, you
        #     keep control of the Ghost"）；英雄只能靠安葬或摧毁幽灵取胜，
        #     由 SeanceRaceMode.check_victory 判定，故这里只声明叛徒条件。
        #   已知简化：叛徒控灵引发的"房屋坍塌"未实现（需整套房间翻转系统，
        #     单独立项）；"降灵完成前禁止一切攻击"未实现。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "seance_race",
        "traitor_rule": "revealer",
        "hero_goal": "在五芒星室完成降灵会并安葬骨头，或在叛徒控鬼后用理智攻击摧毁幽灵。",
        "traitor_goal": "抢先完成降灵会并控制幽灵，之后杀死所有英雄。",
        "suggested_monsters": [],
        "required_cards": ["omen_spirit_board", "omen_ring"],
        "key_rooms": ["pentagram_chamber", "attic", "bedroom", "master_bedroom", "crypt", "graveyard"],
        "tokens": ["knowledge_check", "sanity_check", "ghost", "corpse"],
        "setup": {
            "tracks": {
                "hero_seance": {"label": "英雄降灵会", "target": "half_players_floor", "side": "heroes"},
                "traitor_seance": {"label": "叛徒降灵会", "target": 2, "side": "traitor"},
                "ghost_rest_timer": {"label": "安葬骨头倒计时", "target": 5, "side": "heroes"},
            },
            "flags": {
                "ghost_summoned": False,
                "ghost_control": None,
                "bones_found": False,
                "bones_buried": False,
                "seance_owner_id": None,
                "hero_seance_knowledge": 0,
                "hero_seance_sanity": 0,
                "traitor_seance_knowledge": 0,
                "traitor_seance_sanity": 0,
            },
        },
        "monsters": [
            {"template_id": "ghost", "name": "幽灵", "spawn": "deferred", "speed": 4, "sanity": 6, "attack_attr": "sanity"}
        ],
        "actions": [
            {"id": "seance_check", "side": "both", "stat": ["knowledge", "sanity"], "target": 5, "rooms": ["pentagram_chamber"]},
            # p13：找骨头/安葬都是"If You Summon the Ghost First"之后的任务，
            # 必须英雄先完成降灵并持有幽灵控制权。
            {"id": "find_bones", "side": "heroes", "stat": "knowledge", "target": 5, "rooms": ["attic", "bedroom", "master_bedroom"], "requires": ["flag:ghost_summoned", "flag:ghost_control=heroes"], "set_flags": {"bones_found": True}},
            {"id": "bury_bones", "side": "heroes", "stat": "knowledge", "target": 5, "rooms": ["crypt", "graveyard"], "requires": ["flag:ghost_summoned", "flag:ghost_control=heroes", "flag:bones_found"], "set_flags": {"bones_buried": True}},
        ],
        "win_conditions": [
            {"winner": "traitor", "type": "all_heroes_dead", "reason": "所有英雄都被幽灵与叛徒消灭了。"}
        ],
        "source_pages": [13, 84],
    },
    3: {
        # 校准记录（2026-09-01，对照英雄手册 p14 / 叛徒手册 p85）：
        #   已核对无误：女巫 Speed 4 / Might 3 / Sanity 6（门厅）、猫 3/3/2；
        #               挖根 4+、凡人形态 6+、复原 4+。
        #   本次补齐（实现在 haunt_modes.WitchAndFrogsMode）：
        #     · Root 令牌三株（温室/储藏室/厨房，未发现则发现时悄悄补放）
        #     · 女巫无敌真正生效：引擎此前从不读 invulnerable_until，
        #       现按 monster_specs 判定，女巫在凡人形态施放前无法被选中/攻击
        #     · 女巫法术：蛙皮（同房间理智对决变蛙）+ 鸦翼（飞向最近英雄）
        #     · 青蛙状态机：掉物品/双属性降到最低格（不降骷髅）/禁攻击抽牌探索
        #     · 猫：首蛙出现后生成于作祟房间，追蛙、力量对决吃掉
        #   已知简化：龙息未实现（引擎怪物攻击只在同房间触发）；蛙不能被
        #     拾取携带；人类叛徒施法选目标暂未接 prompter。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "witch_and_frogs",
        "traitor_rule": "revealer",
        "hero_goal": "挖出曼德拉草，带着书在女巫房间施放凡人形态，再攻击杀死女巫。",
        "traitor_goal": "保护女巫，夺走书，把所有英雄杀死或变成青蛙。",
        "suggested_monsters": ["witch"],
        "required_cards": ["omen_book"],
        "key_rooms": ["entrance_hall", "conservatory", "larder", "kitchen"],
        "tokens": ["root", "frog", "cat", "witch"],
        "setup": {
            "tracks": {
                "mortal_form": {"label": "凡人形态法术", "target": 1, "side": "heroes"},
            },
            "flags": {
                "root_found": False,
                "witch_vulnerable": False,
                "cat_spawned": False,
                "pending_roots": [],
            },
        },
        "monsters": [
            {"template_id": "witch", "name": "女巫", "spawn": "room_id", "room_id": "entrance_hall", "speed": 4, "might": 3, "sanity": 6, "invulnerable_until": "witch_vulnerable"},
            {"template_id": "cat", "name": "猫", "spawn": "deferred", "speed": 3, "might": 3, "sanity": 2},
        ],
        "actions": [
            {"id": "dig_root", "side": "heroes", "stat": "knowledge", "target": 4, "set_flags": {"root_found": True}},
            {"id": "cast_mortal_form", "side": "heroes", "stat": "knowledge", "target": 6, "requires": ["omen_book", "same_room:witch"], "progress": "mortal_form", "set_flags": {"witch_vulnerable": True}},
            {"id": "restore_frog", "side": "heroes", "stat": "knowledge", "target": 4, "requires": ["omen_book"]},
            {"id": "carry_frog", "side": "heroes", "label": "背起青蛙", "detail": "把同房间一只没被背着的青蛙像物品一样背起来（p14）。"},
            {"id": "drop_frog", "side": "heroes", "label": "放下青蛙", "detail": "把背着的青蛙放在当前房间（p14）。"},
        ],
        "win_conditions": [
            {"winner": "traitor", "type": "all_heroes_dead", "reason": "所有英雄都被女巫与叛徒消灭了。"}
        ],
        "source_pages": [14, 85],
    },
    4: {
        # 校准记录（2026-09-02，对照英雄手册 p15 / 叛徒手册 p86）：
        #   已核对无误：蜘蛛初始 0/2/5（作祟房）、蛛网 Might 4 防御、
        #               web_damage 目标 = 玩家数、卵第 9 回合孵化、
        #               销毁卵 Knowledge 4+（药膏免检定）、开门 6+。
        #   本次补齐（实现在 haunt_modes.WebEscapeMode）：
        #     · 被困探险者（作祟揭示者不能移动，蛛网破后解困）
        #     · 3-4 人局叛徒被蜘蛛吃掉 / 5-6 人局叛徒在场（p86）
        #     · 蜘蛛按 Turn Traits 逐回合成长（0/2 → 6/8）
        #     · 孵化倒计时 + 蜘蛛追"非揭示者"
        #     · 出屋判定：门开后下一回合在门厅逃出（p15 两步流程的简化）
        #   引擎修复：attack/defense 字段此前被完全忽略（"打蛛网"必成功），
        #     现在按属性对决固定防御值结算——该修复同样惠及剧本 1/5/6。
        #   胜利条件修正：杀叛徒不算英雄胜（原数据又是 traitor_dead 坑）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "web_escape",
        "traitor_rule": "highest_might",
        "hero_goal": "打碎蛛网、摧毁卵，然后打开入口大厅前门并逃出房子。",
        "traitor_goal": "保护蛛卵直到第 9 回合孵化，或杀光英雄。",
        "suggested_monsters": ["giant_spider"],
        "required_cards": ["omen_bite", "item_medical_kit", "item_healing_salve"],
        "key_rooms": ["entrance_hall"],
        "tokens": ["web", "might_check", "eggs", "spider_timer"],
        "setup": {
            "tracks": {
                "web_damage": {"label": "蛛网破坏", "target": "player_count", "side": "heroes"},
                "spider_timer": {"label": "蛛卵孵化倒计时", "target": 9, "side": "traitor"},
            },
            "flags": {
                "revealer_trapped": True,
                "trapped_id": None,
                "web_destroyed": False,
                "eggs_destroyed": False,
                "front_door_open": False,
                "escaped": False,
            },
        },
        "monsters": [
            {"template_id": "giant_spider", "name": "巨型蜘蛛", "spawn": "haunt_room", "speed": 0, "might": 2, "sanity": 5}
        ],
        "actions": [
            # p15：打蛛网必须在蛛网所在房间（作祟揭示的房间）
            {"id": "attack_web", "side": "heroes", "attack": "might", "defense": 4, "label": "蛛网", "progress": "web_damage", "requires": ["same_room:web"]},
            {"id": "destroy_eggs_medical_kit", "side": "heroes", "label": "用医疗箱销毁蛛卵", "stat": "knowledge", "target": 4, "requires": ["item_medical_kit", "same_room:revealer"]},
            {"id": "destroy_eggs_salve", "side": "heroes", "label": "用治疗药膏销毁蛛卵", "requires": ["item_healing_salve", "same_room:revealer"]},
            {"id": "open_front_door", "side": "heroes", "label": "撬开前门", "stat": ["knowledge", "might"], "target": 6, "rooms": ["entrance_hall"], "set_flags": {"front_door_open": True}},
        ],
        "win_conditions": [
            {"winner": "traitor", "type": "all_heroes_dead", "reason": "所有英雄都被巨型蜘蛛杀死了。"}
        ],
        "source_pages": [15, 86],
    },
    5: {
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "werewolf_hunt",
        "traitor_rule": "highest_might",
        "hero_goal": "找到左轮手枪并制作银弹，用银弹射杀所有狼人。",
        "traitor_goal": "感染英雄，把所有英雄杀死或变成狼人。",
        "suggested_monsters": ["dog"],
        "required_cards": ["item_revolver", "omen_dog"],
        "key_rooms": ["attic", "game_room", "junk_room", "master_bedroom", "vault", "research_laboratory", "furnace_room"],
        "tokens": ["wolf", "silver_bullets"],
        "setup": {
            "tracks": {
                "silver_bullets": {"label": "银弹制作", "target": 1, "side": "heroes"},
            },
            "flags": {"revolver_found": False, "silver_bullets_created": False},
        },
        "monsters": [
            {"template_id": "dog", "name": "狗", "spawn": "haunt_room", "speed": 6, "might": 4, "sanity": 3}
        ],
        "actions": [
            {"id": "find_revolver", "side": "heroes", "stat": "knowledge", "target": 5, "rooms": ["attic", "game_room", "junk_room", "master_bedroom", "vault"]},
            {"id": "make_silver_bullets", "side": "heroes", "stat": "knowledge", "target": 5, "rooms": ["research_laboratory", "furnace_room"]},
            {"id": "shoot_werewolf", "side": "heroes", "requires": ["item_revolver", "silver_bullets"], "attack": "speed", "kills": "werewolf"},
        ],
        "source_pages": [16, 87],
    },
    6: {
        # 校准记录（2026-09-02，对照英雄手册 p17 / 叛徒手册 p88）：
        #   已核对无误：外星人 Speed 4 / Might 6 / Sanity 6；数量 3-4 人 1 只、
        #               5-6 人 2 只；破船 Might 5+、目标 = 玩家数。
        #   本次补齐（实现在 haunt_modes.AlienAbductionMode）：
        #     · 叛徒开局"等待运输"出局（p88，物品留在原房间）
        #     · 外星人以理智攻击同房间每个英雄，赢 → 精神控制（无伤）
        #     · 被控者：禁攻击禁行动，回合开始自动移向飞船，到达后下回合上船出局
        #     · 解救：引擎攻击被控同伴取胜 → 半伤（向下取整）+ 解控 + 永久免疫
        #   引擎级新增：immune_to 数据此前从不被读取（与 attack/defense 同类的
        #     "假数据"），现按攻击属性拦截——外星人免疫速度攻击，剧本 1 木乃伊同步生效。
        #   移除了 free_controlled_hero 行动：解救本就是普通攻击 + 引擎半伤
        #     解控逻辑，原数据的 attack 列表 / damage 字段引擎并不支持。
        #   胜利条件修正：叛徒开局就出局，杀叛徒（本就不在场）更不算英雄胜——
        #     英雄胜利只认"飞船瘫痪"（第 5 次修 traitor_dead 坑）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "alien_abduction",
        "traitor_rule": "revealer",
        "hero_goal": "用力量检定破坏宇宙飞船，阻止外星人把英雄带走。",
        "traitor_goal": "控制英雄并把他们带上飞船，或杀光英雄。",
        "suggested_monsters": ["alien"],
        "key_rooms": [],
        "tokens": ["might_check", "spaceship", "alien", "mind_control"],
        "setup": {
            "tracks": {
                "spaceship_damage": {"label": "宇宙飞船破坏", "target": "player_count", "side": "heroes"},
            },
            "flags": {
                "spaceship_disabled": False,
                "ship_room": None,
                "controlled_ids": [],
                "immune_ids": [],
            },
        },
        "monsters": [
            {"template_id": "alien", "name": "外星人", "spawn": "haunt_room", "count": {"lte4": 1, "default": 2}, "speed": 4, "might": 6, "sanity": 6, "immune_to": ["speed_attack"]}
        ],
        "actions": [
            {"id": "damage_spaceship", "side": "heroes", "label": "破坏飞船", "stat": "might", "target": 5, "progress": "spaceship_damage"},
        ],
        "win_conditions": [
            {"winner": "traitor", "type": "all_heroes_dead", "reason": "所有英雄都被外星人带走或杀死了。"}
        ],
        "source_pages": [17, 88],
    },
    7: {
        # 校准记录（2026-09-02，对照英雄手册 p18 / 叛徒手册 p89）：
        #   机制全部落在 CarnivorousIvyMode（根/尖端配对布藤、抓人、拖回根部
        #   吞噬、喷雾制造与喷杀、叛徒毁喷雾、电梯堵塞、叛徒弃书）。
        #   详见 haunt_modes.py 该 handler 的模块注释与已知简化清单。
        #   数值核对无误：尖端 Speed 2 / Might 5 / Sanity 3（p89 底部）；
        #   制造喷雾 Knowledge 5+（p18）；爬行藤对数 = 2×玩家数（上限 10）；
        #   杀满玩家数株即英雄胜；根不移动不可攻击，只有尖端可攻可被攻。
        #   spawn 用 deferred：布藤时机与"每房最多一对"的规则由 handler
        #   控制（引擎的 room_ids 生成会在房间不足时错误地落到作祟房间）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "carnivorous_ivy",
        "traitor_rule": "revealer",
        "hero_goal": "带着书在研究实验室或厨房制作植物喷雾，并用它消灭等同玩家数的爬行物。",
        "traitor_goal": "杀死所有英雄，或毁掉英雄制作出的植物喷雾。",
        "suggested_monsters": ["creeper_tip"],
        "required_cards": ["omen_book"],
        "key_rooms": ["research_laboratory", "kitchen", "chasm", "furnace_room", "underground_lake"],
        "tokens": ["plant_spray", "root", "tip"],
        "setup": {
            "tracks": {
                "creepers_killed": {"label": "已消灭爬行物", "target": "player_count", "side": "heroes"},
            },
            "flags": {"plant_spray_created": False, "plant_spray_destroyed": False},
        },
        "monsters": [
            {
                "template_id": "creeper_tip",
                "name": "爬行藤尖端",
                "spawn": "deferred",
                "count": {"per_player": 2, "max": 10},
                "room_ids": ["entrance_hall", "balcony", "bedroom", "chapel", "conservatory", "dining_room", "garden", "grand_staircase", "graveyard", "master_bedroom", "patio", "tower"],
                "speed": 2,
                "might": 5,
                "sanity": 3,
            }
        ],
        "actions": [
            {
                "id": "make_plant_spray",
                "side": "heroes",
                "label": "制作植物喷雾",
                "detail": "持书在研究实验室或厨房做知识检定（5+）。全书只能造这一瓶。",
                "stat": "knowledge",
                "target": 5,
                "rooms": ["research_laboratory", "kitchen"],
                "requires": ["omen_book"],
                "requires_flags": {"plant_spray_created": False, "plant_spray_destroyed": False},
                "set_flags": {"plant_spray_created": True},
            },
            {
                "id": "spray_creeper",
                "side": "heroes",
                "label": "喷洒植物喷雾",
                "detail": "自动杀死本房间里的一株爬行藤（根或尖端在场即杀整株，不掷骰）。",
                "progress": "creepers_killed",
                "requires_flags": {"plant_spray_destroyed": False},
            },
            {
                "id": "destroy_spray",
                "side": "traitor",
                "label": "毁掉植物喷雾",
                "detail": "把偷来的植物喷雾丢进深坑、熔炉房或地下湖——叛徒直接获胜。",
                "rooms": ["chasm", "furnace_room", "underground_lake"],
                "requires_flags": {"plant_spray_destroyed": False},
                "set_flags": {"plant_spray_destroyed": True},
            },
        ],
        "win_conditions": [
            {"winner": "traitor", "type": "all_heroes_dead", "reason": "所有英雄都被藤蔓吞噬了。"}
        ],
        "source_pages": [18, 89],
    },
    8: {
        # 校准记录（2026-09-02，对照英雄手册 p19 / 叛徒手册 p90）：
        #   机制落在 ExorcismMode：女妖移动计划（掷两骰 0-4 → 传送/贴墙/
        #   直行/操控）、逐房间哀嚎（理智 6+/3-5/0-2 分档伤害）、灵应板
        #   免疫、六个一次性驱魔来源（理智 5+ 或知识 5+，来源用后作废，
        #   检定令牌 = 玩家人数即放逐）。
        #   女妖数值核对无误：Speed 8；不可被攻击。详见 haunt_modes.py
        #   该 handler 的模块注释与已知简化清单。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "exorcism",
        "traitor_rule": "revealer",
        "hero_goal": "用不同的房间或物品完成等同玩家数的驱魔检定，驱逐女妖。",
        "traitor_goal": "保护女妖并杀死所有英雄。",
        "suggested_monsters": ["banshee"],
        "required_cards": ["omen_spirit_board", "omen_holy_symbol", "omen_book", "omen_crystal_ball"],
        "key_rooms": ["chapel", "crypt", "pentagram_chamber", "library", "research_laboratory"],
        "tokens": ["knowledge_check", "sanity_check", "banshee"],
        "setup": {
            "tracks": {
                "exorcism_successes": {"label": "驱魔成功次数", "target": "player_count", "side": "heroes"},
            },
            "flags": {"used_exorcism_sources": []},
        },
        "monsters": [
            {"template_id": "banshee", "name": "女妖", "spawn": "haunt_room", "speed": 8, "might": 0, "sanity": 0, "attack_attr": "sanity", "invulnerable": True}
        ],
        # 八个驱魔行动：id 即来源名（房间用 rooms 限制、物品用 requires 限制），
        # 通用框架负责检定与进度；"同一来源只能成功一次"由 ExorcismMode
        # 按 used_exorcism_sources 过滤。
        "actions": [
            {"id": "chapel", "side": "heroes", "label": "在教堂驱魔", "detail": "理智检定 5+。教堂只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["chapel"], "progress": "exorcism_successes"},
            {"id": "crypt", "side": "heroes", "label": "在地窖驱魔", "detail": "理智检定 5+。地窖只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["crypt"], "progress": "exorcism_successes"},
            {"id": "pentagram_chamber", "side": "heroes", "label": "在五芒星室驱魔", "detail": "理智检定 5+。五芒星室只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["pentagram_chamber"], "progress": "exorcism_successes"},
            {"id": "omen_holy_symbol", "side": "heroes", "label": "借圣徽驱魔", "detail": "理智检定 5+。圣徽只能成功使用一次。", "stat": "sanity", "target": 5, "requires": ["omen_holy_symbol"], "progress": "exorcism_successes"},
            {"id": "omen_spirit_board", "side": "heroes", "label": "借灵应板驱魔", "detail": "理智检定 5+。灵应板只能成功使用一次。", "stat": "sanity", "target": 5, "requires": ["omen_spirit_board"], "progress": "exorcism_successes"},
            {"id": "library", "side": "heroes", "label": "在图书馆驱魔", "detail": "知识检定 5+。图书馆只能成功使用一次。", "stat": "knowledge", "target": 5, "rooms": ["library"], "progress": "exorcism_successes"},
            {"id": "research_laboratory", "side": "heroes", "label": "在研究实验室驱魔", "detail": "知识检定 5+。研究实验室只能成功使用一次。", "stat": "knowledge", "target": 5, "rooms": ["research_laboratory"], "progress": "exorcism_successes"},
            {"id": "omen_book", "side": "heroes", "label": "借古书驱魔", "detail": "知识检定 5+。古书只能成功使用一次。", "stat": "knowledge", "target": 5, "requires": ["omen_book"], "progress": "exorcism_successes"},
            {"id": "omen_crystal_ball", "side": "heroes", "label": "借水晶球驱魔", "detail": "知识检定 5+。水晶球只能成功使用一次。", "stat": "knowledge", "target": 5, "requires": ["omen_crystal_ball"], "progress": "exorcism_successes"},
        ],
        "source_pages": [19, 90],
    },
    9: {
        # 校准记录（2026-09-02，对照英雄手册 p20 / 叛徒手册 p91）：
        #   机制落在 DeathDanceMode：无开局叛徒（引擎指定者开局降回英雄）、
        #   五芒星室与舞厅补房、诱惑检定与堕落转化、放逐提琴手
        #   （理智 5+，圣徽同房即可）、叛徒跳舞检定、毁圣徽即胜。
        #   详见 haunt_modes.py 该 handler 的模块注释与已知简化清单。
        #   说明：resist_music 由模式在回合开始自动执行，不作为点击行动；
        #   banish_fiddler 的"圣徽在房"条件由模式过滤（原文允许不持徽者
        #   在持徽英雄同房时尝试）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "delayed_traitor_relic",
        "traitor_rule": "revealer",
        "hero_goal": "把圣徽带到五芒星室并完成等同初始玩家数的理智检定，驱逐黑暗提琴手。",
        "traitor_goal": "夺取并毁掉圣徽，让死亡之舞继续。",
        "suggested_monsters": [],
        "required_cards": ["omen_holy_symbol"],
        "key_rooms": ["pentagram_chamber", "ballroom", "chasm", "furnace_room", "underground_lake"],
        "tokens": ["sanity_check", "dark_fiddler"],
        "setup": {
            "tracks": {
                "fiddler_banishment": {"label": "驱逐黑暗提琴手", "target": "player_count", "side": "heroes"},
            },
            "flags": {"delayed_traitor": True, "holy_symbol_destroyed": False, "converted_traitor_id": None},
        },
        "actions": [
            {"id": "banish_fiddler", "side": "heroes", "label": "放逐黑暗提琴手", "detail": "圣徽同房时理智检定 5+；成功在五芒星室放一枚理智令牌。", "stat": "sanity", "target": 5, "rooms": ["pentagram_chamber"], "progress": "fiddler_banishment"},
            {"id": "destroy_holy_symbol", "side": "traitor", "label": "毁掉圣徽", "detail": "把偷到手的圣徽丢进深渊、熔炉房或地下湖——叛徒直接获胜。", "rooms": ["chasm", "furnace_room", "underground_lake"], "requires": ["omen_holy_symbol"]},
        ],
        "source_pages": [20, 91],
    },
    10: {
        # 校准记录（2026-09-02，对照英雄手册 p21 / 叛徒手册 p92）：
        #   机制落在 ZombieTrapMode：叛徒开局被疯子杀死、僵尸进特殊房间
        #   自动知识检定（4+ 挣脱，失败永困，每房一只）、疯子 5 点伤害
        #   容量。trap_zombie 行动已删除——困僵尸是僵尸自己走进房间时的
        #   自动结算，不是英雄可点的行动。详见 haunt_modes.py 该 handler
        #   的模块注释与已知简化清单。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "trap_zombies",
        "traitor_rule": "revealer",
        "hero_goal": "把所有僵尸引到特殊房间并困住它们。",
        "traitor_goal": "操控僵尸和疯子杀死所有英雄。",
        "suggested_monsters": ["zombie", "madman"],
        "required_cards": ["omen_madman"],
        "key_rooms": ["master_bedroom", "chapel", "conservatory", "game_room", "library", "attic"],
        "tokens": ["zombie", "madman", "damage_track"],
        "setup": {
            "tracks": {
                "zombies_trapped": {"label": "已困住僵尸", "target": "player_count", "side": "heroes"},
                "madman_damage": {"label": "疯子受到的物理伤害", "target": 5, "side": "heroes"},
            },
            "flags": {"traitor_removed_in_original": True, "trapped_zombies": [], "trapped_rooms": []},
        },
        "monsters": [
            {"template_id": "zombie", "name": "僵尸", "spawn": "omen_rooms", "count": "player_count", "speed": 2, "might": 6, "sanity": 2, "knowledge": 3},
            {"template_id": "madman", "name": "疯子", "spawn": "haunt_room", "speed": 3, "might": 5, "sanity": 5, "damage_capacity": 5},
        ],
        "actions": [],
        "source_pages": [21, 92],
    },
    11: {
        # 校准记录（2026-09-02，对照英雄手册 p22 / 叛徒手册 p93）：
        #   机制落在 SpecterInvasionMode（复用剧本 8 的驱魔底座）：
        #   · 雾中人影（Specter）背面朝下待命于门厅 + 五个朝外窗房间
        #     （大楼梯/主卧/卧室/教堂/餐厅）；疯子（7/7/7）与叛徒开窗放入，
        #     放入当回合即可移动与攻击（p93）
        #   · 疯子每回合自动开最近的窗；全部放入前不攻击（可自卫），之后
        #     才按常规怪物行动
        #   · 雾中人影 Speed 4 / Sanity 6，理智攻击，免疫力量/速度（p93）
        #   · 持戒指者徒手攻击改为理智攻击（引擎 attack_attr_override 钩子），
        #     击败即放逐；被雾中人影攻击而获胜则只是击晕（p22）
        #   · 驱魔：与剧本 8 同款八来源，但理智物品来源用戒指替换灵应板
        #   简化：窗户"假窗"（被邻室挡住即失效）不建模；铃铛/灵应板对
        #   背面人影无效属物品交互边界，未接。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "spectre_exorcism",
        "traitor_rule": "revealer",
        "hero_goal": "用驱魔或持戒指的理智攻击放逐所有雾中人影。",
        "traitor_goal": "让疯子打开窗户放入雾中人影，杀死所有英雄。",
        "suggested_monsters": ["ghost", "madman"],
        "required_cards": ["omen_ring", "omen_holy_symbol", "omen_book", "omen_crystal_ball"],
        "key_rooms": [
            "entrance_hall", "grand_staircase", "master_bedroom", "bedroom",
            "chapel", "dining_room", "crypt", "pentagram_chamber",
            "library", "research_laboratory",
        ],
        "tokens": ["specter", "madman", "sanity_check", "knowledge_check"],
        "setup": {
            "tracks": {
                "exorcism_successes": {"label": "驱魔成功次数", "target": "player_count", "side": "heroes"},
            },
            "flags": {"used_exorcism_sources": [], "specters_activated": 0, "specters_banished": 0},
        },
        "monsters": [
            {"template_id": "ghost", "name": "雾中人影", "spawn": "deferred", "speed": 4, "might": 0, "sanity": 6, "immune_to": ["might", "speed"]},
            {"template_id": "madman", "name": "疯子", "spawn": "deferred", "speed": 7, "might": 7, "sanity": 7},
        ],
        "actions": [
            {"id": "chapel", "side": "heroes", "label": "在教堂驱魔", "detail": "理智检定 5+。教堂只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["chapel"], "progress": "exorcism_successes"},
            {"id": "crypt", "side": "heroes", "label": "在地窖驱魔", "detail": "理智检定 5+。地窖只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["crypt"], "progress": "exorcism_successes"},
            {"id": "pentagram_chamber", "side": "heroes", "label": "在五芒星室驱魔", "detail": "理智检定 5+。五芒星室只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["pentagram_chamber"], "progress": "exorcism_successes"},
            {"id": "omen_holy_symbol", "side": "heroes", "label": "借圣徽驱魔", "detail": "理智检定 5+。圣徽只能成功使用一次。", "stat": "sanity", "target": 5, "requires": ["omen_holy_symbol"], "progress": "exorcism_successes"},
            {"id": "omen_ring", "side": "heroes", "label": "借戒指驱魔", "detail": "理智检定 5+。戒指只能成功使用一次。", "stat": "sanity", "target": 5, "requires": ["omen_ring"], "progress": "exorcism_successes"},
            {"id": "library", "side": "heroes", "label": "在图书馆驱魔", "detail": "知识检定 5+。图书馆只能成功使用一次。", "stat": "knowledge", "target": 5, "rooms": ["library"], "progress": "exorcism_successes"},
            {"id": "research_laboratory", "side": "heroes", "label": "在研究实验室驱魔", "detail": "知识检定 5+。研究实验室只能成功使用一次。", "stat": "knowledge", "target": 5, "rooms": ["research_laboratory"], "progress": "exorcism_successes"},
            {"id": "omen_book", "side": "heroes", "label": "借古书驱魔", "detail": "知识检定 5+。古书只能成功使用一次。", "stat": "knowledge", "target": 5, "requires": ["omen_book"], "progress": "exorcism_successes"},
            {"id": "omen_crystal_ball", "side": "heroes", "label": "借水晶球驱魔", "detail": "知识检定 5+。水晶球只能成功使用一次。", "stat": "knowledge", "target": 5, "requires": ["omen_crystal_ball"], "progress": "exorcism_successes"},
            {"id": "open_window", "side": "traitor", "label": "打开窗户/门", "detail": "在本房间放入一只雾中人影（原版开窗耗 1 格移动，电子版占用剧本行动）。"},
        ],
        "win_conditions": [],
        "source_pages": [22, 93],
    },
    12: {
        # 校准记录（2026-09-02，对照英雄手册 p23 / 叛徒手册 p94）：
        #   机制落在 FleshwalkerMode：无叛徒；邪恶双胞胎（shadow 模板承载，
        #   属性=对应玩家作祟开局值、整局冻结）全部在门厅生成；轮转回合序
        #   天然让怪物阶段落在揭示者回合之后；双胞胎永远追本体、同房优先
        #   攻击本体否则随机（引擎 rng，可复现）；本体死后其双胞胎由该玩家
        #   控制（bot 近似：追最近其他英雄）。
        #   水晶球规则：持球者击败自己的双胞胎即杀死；击败他人双胞胎默认
        #   击晕，持球且其本体已死则杀死；昏迷双胞胎只有持球者能攻击、
        #   防守不反击（monster_counterattack_disabled 钩子）；无球与自己的
        #   双胞胎交手无论胜负四属性各掉 1（on_attack_resolved 钩子）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "fleshwalkers",
        "traitor_rule": "revealer",
        "hero_goal": "在至少一名英雄存活的前提下消灭所有邪恶双胞胎。",
        "traitor_goal": "邪恶双胞胎杀死所有探险者。",
        "suggested_monsters": ["shadow"],
        "required_cards": ["omen_crystal_ball"],
        "key_rooms": ["entrance_hall"],
        "tokens": ["evil_twin"],
        "setup": {
            "tracks": {
                "twins_killed": {"label": "已消灭双胞胎", "target": "player_count", "side": "heroes"},
            },
            "flags": {"twin_of": {}, "twins_killed": 0},
        },
        "monsters": [
            {"template_id": "shadow", "name": "邪恶双胞胎", "spawn": "deferred", "count": "player_count"},
        ],
        "actions": [],
        "win_conditions": [],
        "source_pages": [23, 94],
    },
    13: {
        # 校准记录（2026-09-02，对照英雄手册 p24 / 叛徒手册 p95）：
        #   机制落在 NightmareDreamMode：叛徒（揭示者）当场沉睡——钉住、
        #   掉光物品（狗/女孩/疯子卡一并掉落，属性微调未建模）；
        #   梦魇（shadow 模板承载，5/4/4）数量=玩家数，生成于沉睡房间。
        #   逃脱房间 = 朝外窗房间 + 温室/门厅/花园/墓地/阳台/塔楼；
        #   开局数不足玩家数则从牌堆补房；秘密总数存 flags（联机隐藏
        #   信息裁剪之外的软秘密，热座单机不影响）。
        #   梦魇在未用过的逃脱房间花 1 格移动逃脱（每房限一次，放置逃脱
        #   令牌）；梦魇被杀或逃脱后立即在沉睡房间补一只。
        #   梦魇力量攻击但造成精神伤害；被攻击击败即死、攻击落败照常
        #   击晕（p24/p95）。
        #   唤醒：圣徽被英雄带进沉睡房间，同房任意英雄理智或力量 5+，
        #   成功次数=玩家数即唤醒（味道盐无法唤醒——唤醒链路本就不用它）。
        #   简化：沉睡叛徒仍可被人机界面使用物品（bot 不会；人类界面
        #   未拦，属低风险边界）；沉睡者不可被攻击（attack_allowed）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "nightmare_escape",
        "traitor_rule": "revealer",
        "hero_goal": "把圣徽带进沉睡者的房间，在足够多梦魇逃出屋子前唤醒他。",
        "traitor_goal": "让梦魇按秘密数量逃出房子（逃出数 = 作祟时的逃脱房间数）。",
        "suggested_monsters": ["shadow"],
        "required_cards": ["omen_holy_symbol"],
        "key_rooms": [
            "entrance_hall", "grand_staircase", "master_bedroom", "bedroom",
            "chapel", "dining_room", "conservatory", "garden", "graveyard",
            "patio", "tower", "balcony",
        ],
        "tokens": ["nightmare", "wake_token", "escape"],
        "setup": {
            "tracks": {
                "waking_progress": {"label": "唤醒沉睡者", "target": "player_count", "side": "heroes"},
            },
            "flags": {"sleeper_id": None, "escapes": 0, "escape_total": 0, "escape_used_rooms": []},
        },
        "monsters": [
            {"template_id": "shadow", "name": "梦魇", "spawn": "deferred", "count": "player_count", "speed": 5, "might": 4, "sanity": 4},
        ],
        "actions": [
            {"id": "wake_attempt", "side": "heroes", "label": "唤醒沉睡者", "detail": "圣徽在本房间（任一英雄携带）时，理智或力量检定 5+。", "stat": ["sanity", "might"], "target": 5, "progress": "waking_progress"},
        ],
        "win_conditions": [],
        "source_pages": [24, 95],
    },
    14: {
        # 校准记录（2026-09-02，对照英雄手册 p25 / 叛徒手册 p96）：
        #   机制落在 StarsRightMode：
        #   · 油漆罐（Paint，数量=玩家数）按序放厨房/储藏室/杂物间/储藏室/
        #     实验室/阁楼（不够则同房叠放；全不在场则补房）；英雄一次背一罐，
        #     从相邻有门的房间把罐子扔进五芒星室（原版耗 1 格移动，电子版
        #     占用剧本行动）；所有罐子入室即亵渎胜利
        #   · 狂信徒（4/4/4）数量 = 其他玩家数，生成于五芒星室；力量攻击，
        #     掷出高出 2+ 可改为偷窃（p96）；能搬尸体（移动入房按 2 格计）
        #   · 献祭：叛徒在五芒星室把祭品献上——尸体 4 分 / 狗·女孩·疯子
        #     2 分 / 其他预兆或物品 1 分，累计 13 分即召唤邪神胜利；
        #     被献祭物品移出游戏（进弃牌堆近似）
        #   · 探险者死亡即落尸（引擎新钩子 on_player_died → 尸体令牌）
        #   简化：扔罐"1 格移动"与搬尸"2 格移动"对英雄/叛徒占剧本行动或
        #   移动加倍近似；狂信徒偷窃为 bot 自动（人类叛徒弹窗留待接）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "paint_the_pentagram",
        "traitor_rule": "revealer",
        "hero_goal": "把屋里所有油漆罐扔进五芒星室，亵渎邪教的召唤法阵。",
        "traitor_goal": "献祭凑满 13 分召唤邪神，或杀死所有英雄。",
        "suggested_monsters": ["cultist"],
        "required_cards": [],
        # 原版 Storeroom 在本项目 49 房集中与 Larder（储藏室）共用，
        # 油漆房间序列相应少一间。
        "key_rooms": [
            "pentagram_chamber", "kitchen", "larder", "junk_room",
            "research_laboratory", "attic",
        ],
        "tokens": ["paint", "cultist", "corpse"],
        "setup": {
            "tracks": {
                "desecration": {"label": "已扔进法阵的油漆罐", "target": "player_count", "side": "heroes"},
                "sacrifice_points": {"label": "献祭点数", "target": 13, "side": "traitor"},
            },
            "flags": {"total_cans": 0, "corpse_carrier": {}},
        },
        "monsters": [
            {"template_id": "cultist", "name": "狂信徒", "spawn": "deferred", "count": 1, "speed": 4, "might": 4, "sanity": 4},
        ],
        "actions": [
            {"id": "take_paint", "side": "heroes", "label": "拿起油漆罐", "detail": "捡起本房间的一罐油漆（一次只能背一罐，p25）。"},
            {"id": "throw_paint", "side": "heroes", "label": "扔油漆罐", "detail": "从相邻有门连接的房间把油漆罐扔进五芒星室（原版耗 1 格移动）。"},
            {"id": "take_corpse", "side": "traitor", "label": "背起尸体", "detail": "狂信徒或叛徒把房间的尸体像物品一样背起（入房按 2 格移动，p96）。"},
            {"id": "sacrifice", "side": "traitor", "label": "献祭", "detail": "在五芒星室献上尸体(4分)/狗·女孩·疯子(2分)/其他预兆或物品(1分)。"},
        ],
        "win_conditions": [],
        "source_pages": [25, 96],
    },
    15: {
        # 校准记录（2026-09-02，对照英雄手册 p26 / 叛徒手册 p97）：
        #   机制落在 DragonSiegeMode：
        #   · 巨龙（beast 模板承载，3/8/6）开局在门厅；伤害容量=玩家数；
        #     韧性：每次被击败实扣伤害 -2；免疫速度攻击，持戒指者理智
        #     攻击可伤它（attack_attr_override 复用剧本 11 钩子）
        #   · 每回合两次攻击：火息（同房+门相邻房间的所有探险者含叛徒，
        #     速度检定 4+ 免疫，失败同房 4 骰/相邻 2 骰物理伤害，弃一件
        #     物品减 2 点——bot 自动弃）与咬（力量对决，同房）
        #   · 装备三件套（地下室）：古董护甲（墓穴/地下湖，穿上整回合，
        #     非火焰物理 -5，移动 -1，不可被偷）、盾（深坑/地窖，携带者
        #     免火，移动 -1，同房英雄也免火息）、矛（项目无此卡，改为
        #     令牌放剩余地下室房间；对龙攻击/防御 +4）
        #   简化：穿甲/脱甲的"交给他人"未建模；护甲与盔甲卡不可同穿未拦。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "dragon_siege",
        "traitor_rule": "revealer",
        "hero_goal": "在地下室找到古董护甲、盾与矛，把巨龙的伤害攒满玩家人数并斩杀它。",
        "traitor_goal": "驱使巨龙烧死咬死所有英雄。",
        "suggested_monsters": ["beast"],
        "required_cards": ["omen_ring"],
        "key_rooms": ["entrance_hall", "catacombs", "underground_lake", "chasm", "crypt"],
        "tokens": ["dragon", "antique_armor", "shield", "spear"],
        "setup": {
            "tracks": {
                "dragon_damage": {"label": "巨龙受到的伤害", "target": "player_count", "side": "heroes"},
            },
            "flags": {"worn_by": None, "armor_room": None, "shield_room": None, "spear_room": None},
        },
        "monsters": [
            {"template_id": "beast", "name": "巨龙", "spawn": "deferred", "speed": 3, "might": 8, "sanity": 6, "immune_to": ["speed"]},
        ],
        "actions": [
            {"id": "don_armor", "side": "heroes", "label": "穿上古董护甲", "detail": "花整回穿上（本回合不能移动）：非火焰物理伤害 -5，移动 -1（p26）。"},
            {"id": "take_shield", "side": "heroes", "label": "拿起盾", "detail": "携带者免疫火与热，移动 -1；同房英雄也免疫龙焰（p26）。"},
            {"id": "take_spear", "side": "heroes", "label": "拿起矛", "detail": "对巨龙攻击/防御骰 +4（p26）。"},
        ],
        "win_conditions": [],
        "source_pages": [26, 97],
    },
    16: {
        # 校准记录（2026-09-02，对照英雄手册 p27 / 叛徒手册 p98）：
        #   机制落在 PhantomBombMode：
        #   · 幻影（ghost 模板承载，Speed 0 / Might 6 / Sanity 5）不攻击
        #     只防御；在下一个被发现的带符号地下室房间出现（抑制该次抽牌
        #     ——引擎 suppress_room_draw 钩子），伴女孩令牌与"到访标记"；
        #     被击败即死、英雄获女孩；防御成功即带女孩逃走，下次再出现
        #   · 拆弹：在击败幻影的房间做知识 7+（每回合一次）
        #   · 逃脱：门厅开前门（知识/力量 6+），持女孩者回合结束仍站门厅
        #     即带她逃出（原文的群体逃跑简化为持女孩者出门）
        #   · 炸弹计时：叛徒回合开始推进计时器并掷等量骰，掷出阈值以上
        #     房子爆炸（3人8+/4人7+/5人6+/6人5+）；"回合结束"用"下一回合
        #     开始"近似（时序等价，见类注释）
        #   简化：开成功门后"抽事件卡"步骤未建模；地下室全部探索完且
        #     幻影仍存活的"叛徒指定房间"分支未建模（出现依赖发现）；叛徒
        #     阵亡后计时器冻结（引擎怪物代跑惯例下的保守处理）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "phantom_bomb",
        "traitor_rule": "revealer",
        "hero_goal": "在地下室击败守着女孩的幻影，再拆掉炸弹或带她从前门逃出。",
        "traitor_goal": "让房子炸上天，或让梦魇般的幻影耗死所有英雄。",
        "suggested_monsters": ["ghost"],
        "required_cards": [],
        "key_rooms": ["entrance_hall", "catacombs", "crypt", "furnace_room", "basement_landing"],
        "tokens": ["phantom", "girl", "phantom_mark"],
        "setup": {
            "tracks": {
                "bomb_timer": {"label": "炸弹计时", "target": 20, "side": "traitor"},
            },
            "flags": {
                "girl_rescued": False, "bomb_defused": False, "front_door_open": False,
                "escaped": False, "bomb_room": None, "girl_holder_id": None,
            },
        },
        "monsters": [
            {"template_id": "ghost", "name": "幻影", "spawn": "deferred", "speed": 0, "might": 6, "sanity": 5},
        ],
        "actions": [
            {"id": "defuse_bomb", "side": "heroes", "label": "拆除炸弹", "detail": "在击败幻影的房间做知识检定 7+（每回合一次，p27）。", "stat": "knowledge", "target": 7, "requires_flags": {"girl_rescued": True}, "set_flags": {"bomb_defused": True}},
            {"id": "open_front_door", "side": "heroes", "label": "打开前门", "detail": "门厅里开锁（知识 6+）或破门（力量 6+）；成功后持女孩者可从门厅逃出（p27）。", "stat": ["knowledge", "might"], "target": 6, "rooms": ["entrance_hall"], "requires_flags": {"front_door_open": False}, "set_flags": {"front_door_open": True}},
        ],
        "win_conditions": [],
        "source_pages": [27, 98],
    },
    17: {
        # 校准记录（2026-09-02，对照英雄手册 p28 / 叛徒手册 p99）：
        #   机制落在 BugSprayMode：
        #   · 六种配料令牌按序放实验室/储藏室/阁楼/仆人房/厨房/花园
        #     （未发现则发现时补放）；英雄拾取任意三种带进实验室或厨房
        #     （不拘谁拿着），知识 4+ 合成杀虫剂（每回合一次；失败保留
        #     配料下回合再试）
        #   · 六只虫（Praying Mantis 4/5/4、Centipede 3/3/4、Wasp 5/2/4、
        #     Spider 3/6/4、Roach 0/5/4、Beetle 3/6/4）全部用 spider 模板
        #     承载，种类映射存 flags["bug_kind"]（项目无昆虫模板，
        #     优化方案 engine_note 惯例）；原版 Storeroom 与 Larder 共用
        #   · 杀虫剂攻击：速度攻击（attack_attr_override）；用杀虫剂
        #     击败即杀（杀满三只其余逃散）；用杀虫剂落败不受伤
        #     （attack_loss_damage_disabled）
        #   · 蛛网：被蜘蛛击败的探险者被缚（四属性各 -2、不低于 1、
        #     不能移动），同房任意探险者每回合一次力量 5+ 挣脱并恢复
        #   · 蟑螂：永不离开厨房；离开厨房按 3 格计（movement_cost_floor）
        #   · 叛徒：拾取/偷取配料（至多 3 枚）或夺杀虫剂（1 件且不带
        #     配料），在深坑/熔炉房/地下湖销毁；4 枚配料被毁且英雄无
        #     杀虫剂 → 叛徒胜
        #   简化：英雄丢下配料未建模（一次性拾取）；人类叛徒的选择
        #     弹窗留待接 prompter。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "bug_spray",
        "traitor_rule": "revealer",
        "hero_goal": "集齐三种配料合成杀虫剂，用速度攻击毒杀三只巨虫。",
        "traitor_goal": "毁掉四枚配料且英雄没有杀虫剂，或让虫群吃掉所有英雄。",
        "suggested_monsters": ["spider"],
        "required_cards": [],
        "key_rooms": [
            "research_laboratory", "larder", "attic", "servants_quarters",
            "kitchen", "garden", "junk_room", "crypt", "chasm",
            "furnace_room", "underground_lake",
        ],
        "tokens": ["ingredient", "bug_spray", "mantis", "centipede", "wasp", "spider_bug", "roach", "beetle"],
        "setup": {
            "tracks": {
                "bugs_killed": {"label": "已被毒杀的巨虫", "target": 3, "side": "heroes"},
                "ingredients_destroyed": {"label": "被毁配料", "target": 4, "side": "traitor"},
            },
            "flags": {"bug_kind": {}, "webbed": [], "spray_destroyed": False},
        },
        "monsters": [
            {"template_id": "spider", "name": "巨虫", "spawn": "deferred", "count": 6},
        ],
        "actions": [
            {"id": "take_ingredient", "side": "any", "label": "拾取配料", "detail": "捡起本房间的一枚配料（叛徒至多背 3 枚，p99）。"},
            {"id": "make_spray", "side": "heroes", "label": "调配杀虫剂", "detail": "在实验室或厨房集齐三枚配料（不拘谁拿着）后做知识 4+（p28）。", "stat": "knowledge", "target": 4, "rooms": ["research_laboratory", "kitchen"]},
            {"id": "destroy_ingredient", "side": "traitor", "label": "销毁配料", "detail": "在深坑/熔炉房/地下湖把背着的配料或杀虫剂毁掉（p99）。", "rooms": ["chasm", "furnace_room", "underground_lake"]},
            {"id": "break_webs", "side": "any", "label": "挣脱蛛网", "detail": "同房有被缚探险者时做力量 5+，解放并恢复其属性（p99）。", "stat": "might", "target": 5},
        ],
        "win_conditions": [],
        "source_pages": [28, 99],
    },
    18: {
        # 校准记录（2026-09-02，对照英雄手册 p29 / 叛徒手册 p100）：
        #   机制落在 OffspringMode：
        #   · 花朵：在温室/花园/墓地做知识 5+ 发现（花 token 挂到发现者
        #     身上，不可被偷——令牌天然满足）；带进毒藤房间后，房内每个
        #     英雄知识 5+ 削弱，3-4 人局 2 次成功 / 5-6 人局 3 次杀死毒藤
        #   · 孢子：毒藤房间开局有玩家数枚；叛徒每回合按其他人数加 2-3 枚
        #     （当回合即可移动，bot 每枚每回合向最近英雄爬 1 格）
        #   · 孢子伤害：回合开始处于或移动经过带孢子的房间，各 1 骰物理
        #     （多枚不叠加；盔甲不防——引擎按 source="孢子" 豁免）
        #   · 屏息：在无孢子房间可屏息移动（格数=力量），下一回合不能移动
        #     （可行动），再下回合恢复；屏息回合结束身处孢子房则 1 骰
        #   简化：屏息以剧本行动近似"回合开始可选"；孢子不使用电梯未
        #     过滤（bot 沿最短路爬行，电梯链极少成为通路）；毒藤本体
        #     不可被攻击（p29 孢子不可攻击，藤由削弱检定杀死）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "poisonous_plant",
        "traitor_rule": "revealer",
        "hero_goal": "找到花朵带进毒藤房间，用知识削弱并杀死毒藤，躲开孢子。",
        "traitor_goal": "让毒藤的孢子铺满房子，杀死所有英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["conservatory", "garden", "graveyard", "chasm", "furnace_room", "underground_lake"],
        "tokens": ["evil_plant", "spore", "flower", "knowledge_check"],
        "setup": {
            "tracks": {
                "weaken_count": {"label": "对毒藤的削弱", "target": 3, "side": "heroes"},
            },
            "flags": {
                "flower_found": False, "weaken_count": 0, "plant_room": None,
                "plant_killed": False, "breath_active": {}, "catching_breath": [],
            },
        },
        "monsters": [],
        "actions": [
            {"id": "find_flower", "side": "heroes", "label": "寻找花朵", "detail": "在温室/花园/墓地做知识 5+，找到能杀死毒藤的花（p29）。", "stat": "knowledge", "target": 5, "rooms": ["conservatory", "garden", "graveyard"], "requires_flags": {"flower_found": False}, "set_flags": {"flower_found": True}},
            {"id": "weaken_plant", "side": "heroes", "label": "削弱毒藤", "detail": "花朵在本房间时做知识 5+；成功次数足够即杀死毒藤（p29）。", "stat": "knowledge", "target": 5, "progress": "weaken_count", "requires_flags": {"flower_found": True}},
            {"id": "hold_breath", "side": "heroes", "label": "屏住呼吸", "detail": "在无孢子房间屏息移动（格数=力量）；下一回合不能移动（p29）。"},
        ],
        "win_conditions": [],
        "source_pages": [29, 100],
    },
}


def get_haunt_rule_override(haunt_id: int) -> dict[str, Any]:
    return deepcopy(HAUNT_RULE_OVERRIDES.get(haunt_id, {}))


# ---------------------------------------------------------------------------
# 11-70 号剧本的结构化规则
#
# 这组数据是程序规则层，不是玩家手册的替代品。每个剧本都有自己的
# mode、目标、关键房间、资源、行动和胜负条件；共享的是引擎执行方式。
# 原版中的幽灵、蝙蝠、恶魔等组件在当前组件库中没有独立模板时，使用
# 最接近的现有模板，并在 engine_note 中保留映射说明，避免把缺少组件
# 误标成“没有规则”。


def _scenario_action(
    action_id: str,
    side: str,
    label: str,
    stat: str | list[str],
    target: int,
    rooms: tuple[str, ...],
    progress: str,
    detail: str,
    requires: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": action_id,
        "side": side,
        "label": label,
        "detail": detail,
        "stat": stat,
        "target": target,
        "rooms": list(rooms),
        "progress": progress,
        "requires": list(requires),
    }


def _make_scenario_rule(
    haunt_id: int,
    *,
    mode: str,
    traitor_rule: str,
    hero_goal: str,
    traitor_goal: str,
    rooms: tuple[str, ...],
    monsters: tuple[str, ...],
    tokens: tuple[str, ...],
    hero_task: str,
    traitor_task: str,
    hero_stat: str | list[str] = "knowledge",
    traitor_stat: str | list[str] = "might",
    hero_target: int = 5,
    traitor_target: int = 5,
    hero_progress_target: int | str = "player_count",
    traitor_progress_target: int | str = "player_count",
    hero_win_type: str = "track",
    hero_win_target: int | str | None = None,
    traitor_win_type: str = "all_heroes_dead",
    required_cards: tuple[str, ...] = (),
    hero_requires: tuple[str, ...] = (),
    traitor_requires: tuple[str, ...] = (),
    monster_count: int | str | dict[str, int] = 1,
    hero_detail: str = "成功后推进英雄目标轨道。",
    traitor_detail: str = "成功后推进叛徒目标轨道。",
    engine_note: str = "使用当前组件库中的近似怪物模板；玩家规则以对应剧本文本为准。",
) -> dict[str, Any]:
    hero_win_target = hero_win_target if hero_win_target is not None else hero_progress_target
    monster_specs = [
        {
            "template_id": template_id,
            "spawn": "haunt_room",
            "count": monster_count if index == 0 else 1,
        }
        for index, template_id in enumerate(monsters)
    ]
    rule: dict[str, Any] = {
        "version": 2,
        "fidelity": "skeleton",
        "status": "playable",
        "mode": mode,
        "traitor_rule": traitor_rule,
        "hero_goal": hero_goal,
        "traitor_goal": traitor_goal,
        "suggested_monsters": list(monsters),
        "required_cards": list(required_cards),
        "key_rooms": list(rooms),
        "tokens": list(tokens),
        "setup": {
            "tracks": {
                "hero_progress": {
                    "label": f"英雄：{hero_task}",
                    "target": hero_progress_target,
                    "side": "heroes",
                },
                "traitor_progress": {
                    "label": f"叛徒：{traitor_task}",
                    "target": traitor_progress_target,
                    "side": "traitor",
                },
            },
            "flags": {
                "scenario_started": True,
                "hero_sources_used": [],
                "traitor_sources_used": [],
            },
        },
        "monsters": monster_specs,
        "actions": [
            _scenario_action(
                f"h{haunt_id}_hero_task",
                "heroes",
                hero_task,
                hero_stat,
                hero_target,
                rooms,
                "hero_progress",
                hero_detail,
                hero_requires,
            ),
            _scenario_action(
                f"h{haunt_id}_traitor_task",
                "traitor",
                traitor_task,
                traitor_stat,
                traitor_target,
                rooms,
                "traitor_progress",
                traitor_detail,
                traitor_requires,
            ),
        ],
        "win_conditions": [
            {
                "winner": "heroes",
                "type": hero_win_type,
                "track": "hero_progress" if hero_win_type == "track" else None,
                "operator": ">=",
                "target": hero_win_target,
                "reason": hero_goal,
            },
            {
                "winner": "traitor",
                "type": traitor_win_type,
                "track": "traitor_progress" if traitor_win_type == "track" else None,
                "operator": ">=",
                "target": traitor_progress_target,
                "reason": traitor_goal,
            },
        ],
        "source_pages": [11 + haunt_id, 82 + haunt_id],
        "engine_note": engine_note,
    }
    return rule


_SUPPLEMENTAL_SCENARIOS: dict[int, dict[str, Any]] = {
    19: dict(mode="beastmaster", traitor_rule="revealer", hero_goal="用特殊攻击夺走长矛，使兽王恢复正常。", traitor_goal="指挥动物爪牙杀死所有英雄。", rooms=("entrance_hall", "underground_lake", "garden", "graveyard", "patio", "balcony", "tower"), monsters=("beast", "wolf"), tokens=("spear", "animal_minion", "bear", "hawk"), hero_task="夺取兽王长矛", traitor_task="召集动物爪牙", hero_stat=["might", "sanity"], hero_target=5, hero_progress_target=1, hero_detail="与兽王同房间时完成特殊夺取行动，不把兽王杀死。", traitor_detail="推进动物爪牙威胁轨道。", monster_count="player_count", hero_win_target=1),
    20: dict(mode="ghost_bride", traitor_rule="revealer", hero_goal="找到戒指和真正新郎的尸体，并在小教堂阻止错误婚礼。", traitor_goal="让幽灵新娘在小教堂完成婚礼，或杀死所有英雄。", rooms=("crypt", "graveyard", "chapel", "catacombs", "entrance_hall"), monsters=("ghost",), tokens=("bride", "groom", "ring", "corpse"), hero_task="揭穿并阻止幽灵婚礼", traitor_task="完成幽灵婚礼", hero_stat="knowledge", hero_target=5, hero_progress_target=2, hero_detail="先找齐戒指和尸体，再在小教堂完成阻止仪式。", traitor_detail="在小教堂推动婚礼进度。", monster_count=1, hero_win_target=2, traitor_win_type="track", traitor_progress_target=2),
    21: dict(mode="zombie_lord", traitor_rule="revealer", hero_goal="摧毁僵尸领主或消灭所有僵尸。", traitor_goal="让僵尸领主和僵尸杀死所有英雄。", rooms=("crypt", "graveyard", "entrance_hall", "underground_lake", "garden", "chapel", "conservatory", "pentagram_chamber"), monsters=("zombie", "giant"), tokens=("zombie_lord", "zombie", "damage"), hero_task="清理僵尸并攻击领主", traitor_task="召集僵尸围攻", hero_stat="might", hero_target=5, hero_detail="在僵尸威胁区域完成清理行动。", traitor_detail="让僵尸推进围攻轨道。", monster_count="player_count"),
    22: dict(mode="abyss_exorcism", traitor_rule="revealer", hero_goal="完成与玩家数相等的驱魔检定，阻止房屋坍入深渊。", traitor_goal="让房屋不断坍塌并杀死所有英雄。", rooms=("chasm", "chapel", "crypt", "pentagram_chamber", "library", "research_laboratory"), monsters=("shadow",), tokens=("sanity_check", "knowledge_check", "abyss"), hero_task="驱魔稳定房屋", traitor_task="加速深渊坍塌", hero_stat=["sanity", "knowledge"], hero_target=5, hero_detail="在指定房间或使用指定物品完成一次驱魔。", traitor_detail="推进坍塌倒计时。", monster_count=1),
    23: dict(mode="tentacled_horror", traitor_rule="revealer", hero_goal="摧毁触手生物。", traitor_goal="让触手逐渐增强并杀死所有英雄。", rooms=("furnace_room", "conservatory", "organ_room", "underground_lake", "garden", "chasm"), monsters=("giant",), tokens=("tentacle_root", "tentacle_tip", "time"), hero_task="定位并摧毁触手", traitor_task="增强触手", hero_stat="might", hero_target=6, hero_progress_target=1, hero_detail="在触手所在房间完成一次破坏行动。", traitor_detail="推进触手增长轨道。", monster_count="player_count", hero_win_target=1),
    24: dict(mode="bat_exodus", traitor_rule="revealer", hero_goal="用风琴赶走蝙蝠并消灭附着的蝙蝠。", traitor_goal="让蝙蝠吸取英雄生命，或杀死所有英雄。", rooms=("organ_room", "entrance_hall", "balcony", "garden", "graveyard", "patio", "tower"), monsters=("spider",), tokens=("bat", "organ", "victim"), hero_task="演奏风琴驱逐蝙蝠", traitor_task="扩散蝙蝠", hero_stat="knowledge", hero_target=5, hero_progress_target="player_count", hero_detail="在风琴房完成驱逐检定。", traitor_detail="推进蝙蝠侵袭轨道。", monster_count="player_count"),
    25: dict(mode="voodoo_dolls", traitor_rule="revealer", hero_goal="找到并摧毁所有巫毒娃娃，同时让至少一半英雄存活。", traitor_goal="让娃娃的诅咒杀死英雄。", rooms=("bloody_room", "larder", "crypt", "junk_room", "vault", "attic", "kitchen"), monsters=("cultist",), tokens=("voodoo_doll", "curse", "time"), hero_task="寻找并摧毁巫毒娃娃", traitor_task="加深娃娃诅咒", hero_stat="knowledge", hero_target=5, hero_progress_target="player_count", hero_detail="在娃娃可能出现的房间完成搜寻和摧毁。", traitor_detail="推进诅咒强度轨道。", monster_count=1),
    26: dict(mode="rat_ritual", traitor_rule="revealer", hero_goal="消灭房屋内所有老鼠，阻止五芒星室的仪式。", traitor_goal="完成老鼠仪式，或杀死所有英雄。", rooms=("pentagram_chamber", "kitchen", "larder", "junk_room", "crypt"), monsters=("spider",), tokens=("rat", "ritual", "sanity_check"), hero_task="清除老鼠", traitor_task="完成老鼠仪式", hero_stat="might", hero_target=5, hero_progress_target="player_count", hero_detail="逐个清除老鼠标记。", traitor_detail="在五芒星室推进仪式轨道。", monster_count="player_count"),
    27: dict(mode="blob_weakness", traitor_rule="revealer", hero_goal="发现斑点弱点并用正确配方摧毁 Blob。", traitor_goal="让斑点扩散并杀死所有英雄。", rooms=("research_laboratory", "kitchen", "furnace_room", "chasm", "underground_lake"), monsters=("plant",), tokens=("blob", "knowledge_check", "formula"), hero_task="研究斑点弱点", traitor_task="扩散斑点", hero_stat="knowledge", hero_target=3, hero_progress_target=2, hero_detail="在斑点标记相邻房间完成研究，随后完成化学配方。", traitor_detail="推进斑点扩散轨道。", monster_count=1, hero_win_target=2),
    28: dict(mode="demon_ring", traitor_rule="revealer", hero_goal="携带戒指击败恶魔领主两次。", traitor_goal="让恶魔从地狱之门涌入并杀死所有英雄。", rooms=("chasm", "furnace_room", "underground_lake", "pentagram_chamber", "chapel"), monsters=("giant",), tokens=("demon_lord", "demon", "hell_gate"), hero_task="用戒指放逐恶魔领主", traitor_task="召唤恶魔", hero_stat=["might", "sanity"], hero_target=5, hero_progress_target=2, hero_detail="携带戒指在恶魔领主所在房间完成一次放逐攻击。", traitor_detail="推进地狱之门召唤进度。", monster_count="player_count", hero_win_target=2, hero_requires=("omen_ring",)),
    29: dict(mode="frankenstein_fire", traitor_rule="revealer", hero_goal="用火焰弱点摧毁弗兰肯斯坦怪物。", traitor_goal="命令怪物杀死所有英雄。", rooms=("furnace_room", "kitchen", "attic", "research_laboratory"), monsters=("giant",), tokens=("torch", "fire", "monster"), hero_task="准备火焰并击破怪物", traitor_task="增强弗兰肯斯坦怪物", hero_stat="knowledge", hero_target=5, hero_progress_target=1, hero_detail="在火焰相关房间准备武器，再攻击怪物。", traitor_detail="推进怪物力量轨道。", monster_count=1, hero_win_target=1),
    30: dict(mode="dracula_rising", traitor_rule="revealer", hero_goal="摧毁德古拉伯爵和新娘。", traitor_goal="在阳光削弱吸血鬼前杀死或转化所有英雄。", rooms=("crypt", "graveyard", "bloody_room", "chapel", "balcony", "tower"), monsters=("shadow", "beast"), tokens=("dracula", "bride", "blood", "sun"), hero_task="猎杀德古拉与新娘", traitor_task="汲取鲜血", hero_stat="sanity", hero_target=5, hero_progress_target=2, hero_detail="在吸血鬼所在房间完成两次猎杀行动。", traitor_detail="推进德古拉苏醒与鲜血轨道。", monster_count=2, hero_win_target=2),
    31: dict(mode="living_house", traitor_rule="revealer", hero_goal="用长矛击败房屋的心脏或大脑。", traitor_goal="让活房屋消化并杀死所有英雄。", rooms=("organ_room", "attic", "dining_room", "kitchen", "larder", "crypt"), monsters=("plant",), tokens=("heart", "brain", "stomach", "antibody"), hero_task="攻击房屋心脏或大脑", traitor_task="消化入侵者", hero_stat="might", hero_target=6, hero_progress_target=2, hero_detail="在风琴房或阁楼完成一次长矛攻击行动。", traitor_detail="推进房屋消化轨道。", monster_count=1, hero_win_target=2),
    32: dict(mode="lost_dimension", traitor_rule="revealer", hero_goal="让房屋恢复到英雄所在的维度。", traitor_goal="让有毒维度持续伤害英雄，或杀死所有英雄。", rooms=("organ_room", "entrance_hall", "foyer", "grand_staircase", "basement_landing"), monsters=("shadow",), tokens=("dimension", "poison", "anchor"), hero_task="修复维度锚点", traitor_task="维持异维度", hero_stat="knowledge", hero_target=5, hero_progress_target="player_count", hero_detail="在风琴房或起始房间完成维度修复检定。", traitor_detail="推进异维度污染轨道。", monster_count=1),
    33: dict(mode="lake_rescue", traitor_rule="revealer", hero_goal="在女孩溺水前从地下湖救出她。", traitor_goal="把女孩喂给湖中生物，或杀死所有英雄。", rooms=("underground_lake", "basement_landing", "crypt", "furnace_room"), monsters=("beast",), tokens=("girl", "lake", "drowning"), hero_task="从地下湖救出女孩", traitor_task="把女孩带向湖中生物", hero_stat="might", hero_target=5, hero_progress_target=1, hero_detail="在地下湖或湖区完成救援行动。", traitor_detail="推进溺水倒计时。", monster_count=1, hero_win_target=1),
    34: dict(mode="mad_world", traitor_rule="revealer", hero_goal="把疯子锁入保险库，并杀死或锁住叛徒。", traitor_goal="让凯撒和疯子仆从杀死所有英雄。", rooms=("vault", "master_bedroom", "chapel", "conservatory", "game_room", "library", "attic"), monsters=("madman",), tokens=("vault_lock", "madman", "senator"), hero_task="锁住疯子", traitor_task="煽动疯子仆从", hero_stat="knowledge", hero_target=6, hero_progress_target=1, hero_detail="把疯子引到保险库并完成锁门检定。", traitor_detail="推进疯子仆从的围攻轨道。", monster_count="player_count", hero_win_target=1),
    35: dict(mode="small_change_escape", traitor_rule="revealer", hero_goal="让至少一半英雄使用玩具飞机从外缘逃脱。", traitor_goal="让猫吃掉所有缩小的英雄。", rooms=("balcony", "garden", "graveyard", "patio", "tower", "entrance_hall", "foyer"), monsters=("cat",), tokens=("toy_plane", "cat", "small_hero"), hero_task="驾驶玩具飞机逃脱", traitor_task="驱使猫捕食", hero_stat="speed", hero_target=5, hero_progress_target="half_players_ceil", hero_detail="在有外缘出口的房间完成一次逃脱行动。", traitor_detail="推进猫的捕食轨道。", monster_count="player_count", hero_win_target="half_players_ceil"),
    36: dict(mode="swamp_escape", traitor_rule="revealer", hero_goal="至少一半原英雄活着逃离房屋，并不能留下其他活着的英雄。", traitor_goal="让房屋沉入沼泽，或杀死所有英雄。", rooms=("attic", "entrance_hall", "foyer", "grand_staircase", "garden", "patio"), monsters=("shadow",), tokens=("rowboat", "swamp", "escape"), hero_task="组织逃离房屋", traitor_task="加速沼泽下沉", hero_stat="might", hero_target=5, hero_progress_target="half_players_ceil", hero_detail="在入口大厅准备船并完成一次逃离。", traitor_detail="推进沼泽下沉轨道。", monster_count=1, hero_win_target="half_players_ceil"),
    37: dict(mode="death_checkmate", traitor_rule="revealer", hero_goal="在死亡的棋局中完成一次胜利检定。", traitor_goal="让死亡在无对手时赢下棋局，或杀死所有英雄。", rooms=("vault", "crypt", "research_laboratory", "operating_laboratory", "game_room"), monsters=("shadow",), tokens=("death", "seal", "chess"), hero_task="在棋局中战胜死亡", traitor_task="逼迫死亡弃局", hero_stat="knowledge", hero_target=6, hero_progress_target=1, hero_detail="与死亡同房间时完成知识检定；圣印可提供帮助。", traitor_detail="推进死亡的棋局压力。", monster_count=1, hero_win_target=1),
    38: dict(mode="hellbats_exorcism", traitor_rule="revealer", hero_goal="完成驱魔，把火蝠赶出房屋。", traitor_goal="用火蝠吸取英雄的血，或杀死所有英雄。", rooms=("chapel", "crypt", "pentagram_chamber", "library", "research_laboratory"), monsters=("spider",), tokens=("fire_bat", "exorcism", "blood"), hero_task="驱魔火蝠", traitor_task="喂养火蝠", hero_stat=["sanity", "knowledge"], hero_target=5, hero_progress_target="player_count", hero_detail="在驱魔房间累计成功检定。", traitor_detail="推进火蝠繁殖轨道。", monster_count="half_players_ceil"),
    39: dict(mode="secret_heir", traitor_rule="revealer", hero_goal="让真正继承人坐上雕像走廊的王座，并持有长矛和戒指。", traitor_goal="杀死秘密继承人，或杀死所有英雄。", rooms=("statuary_corridor", "gallery", "entrance_hall", "foyer"), monsters=("cultist",), tokens=("heir", "assassin", "throne"), hero_task="确认继承人并登上王座", traitor_task="寻找并刺杀继承人", hero_stat="knowledge", hero_target=5, hero_progress_target=1, hero_detail="在雕像走廊完成继承仪式。", traitor_detail="推进刺客锁定轨道。", monster_count="player_count", hero_win_target=1, required_cards=("omen_spear", "omen_ring"), hero_requires=("omen_spear", "omen_ring")),
    40: dict(mode="buried_alive", traitor_rule="revealer", hero_goal="在被埋的朋友死亡前挖出他。", traitor_goal="让被埋者窒息，或杀死所有英雄。", rooms=("catacombs", "crypt", "furnace_room", "basement_landing", "junk_room"), monsters=("zombie",), tokens=("buried_friend", "might_check", "time"), hero_task="挖出被埋者", traitor_task="加速窒息倒计时", hero_stat="might", hero_target=5, hero_progress_target=1, hero_detail="在秘密埋葬房间完成力量检定；通灵板可协助定位。", traitor_detail="推进窒息倒计时。", monster_count=1, hero_win_target=1),
    41: dict(mode="invisible_traitor", traitor_rule="revealer", hero_goal="找到并击败隐形叛徒。", traitor_goal="利用隐形状态杀死所有英雄。", rooms=("entrance_hall", "foyer", "grand_staircase", "library", "chapel"), monsters=("shadow",), tokens=("invisible", "tracking", "blind_fight"), hero_task="追踪隐形叛徒", traitor_task="隐形袭击英雄", hero_stat="knowledge", hero_target=5, hero_progress_target=1, hero_detail="根据叛徒攻击留下的线索完成追踪检定。", traitor_detail="推进隐形袭击轨道。", monster_count=1, hero_win_target=1),
    42: dict(mode="hell_gate_hero", traitor_rule="revealer", hero_goal="杀死叛徒并关闭地狱之门。", traitor_goal="通过活人献祭打开地狱之门，或杀死所有英雄。", rooms=("pentagram_chamber", "chasm", "chapel", "crypt", "entrance_hall"), monsters=("giant",), tokens=("statue", "hell_gate", "sacrifice"), hero_task="关闭地狱之门", traitor_task="完成活人献祭", hero_stat="knowledge", hero_target=6, hero_progress_target=1, hero_detail="在五芒星室或入口大厅完成关闭仪式。", traitor_detail="推进地狱之门开启轨道。", monster_count=1, hero_win_target=1, traitor_win_type="track", traitor_progress_target="player_count"),
    43: dict(mode="shadow_exorcism", traitor_rule="revealer", hero_goal="完成光之仪式，在英雄影子进入五芒星室前驱逐暗影。", traitor_goal="让影子抵达五芒星室并把英雄变成幽灵。", rooms=("chapel", "library", "pentagram_chamber", "entrance_hall", "grand_staircase"), monsters=("shadow",), tokens=("shadow", "light_ritual", "sanity_check"), hero_task="完成光之仪式", traitor_task="推进影子入侵", hero_stat=["sanity", "knowledge"], hero_target=5, hero_progress_target="player_count", hero_detail="在小教堂或图书馆完成光之仪式。", traitor_detail="推进影子向五芒星室移动的轨道。", monster_count="player_count"),
    44: dict(mode="supernatural_aging", traitor_rule="revealer", hero_goal="停止超自然衰老过程。", traitor_goal="让所有英雄因衰老失去战斗能力，或杀死所有英雄。", rooms=("library", "chapel", "research_laboratory", "operating_laboratory", "statuary_corridor"), monsters=("shadow",), tokens=("aging", "badge", "sanity_check", "knowledge_check"), hero_task="停止衰老", traitor_task="加速衰老", hero_stat=["knowledge", "sanity"], hero_target=5, hero_progress_target="player_count", hero_detail="在知识或精神检定来源处移除衰老标记。", traitor_detail="推进衰老轨道。", monster_count=1),
    45: dict(mode="bomb_defusal", traitor_rule="revealer", hero_goal="拆除所有英雄身上的定时炸弹并阻止大炸弹。", traitor_goal="引爆炸弹或杀死所有英雄。", rooms=("entrance_hall", "foyer", "research_laboratory", "furnace_room", "vault"), monsters=("giant",), tokens=("bomb", "big_bomb", "timer"), hero_task="拆除定时炸弹", traitor_task="推进大炸弹倒计时", hero_stat="knowledge", hero_target=5, hero_progress_target="player_count", hero_detail="在入口大厅或实验室完成一次拆弹行动。", traitor_detail="推进大炸弹倒计时，达到目标即爆炸。", monster_count=1, traitor_win_type="track", traitor_progress_target=5),
    46: dict(mode="cannibal_feast", traitor_rule="revealer", hero_goal="让所有受害者和英雄逃离，或击败叛徒与食人怪。", traitor_goal="完成盛宴并强化食人怪，或杀死所有英雄。", rooms=("attic", "entrance_hall", "foyer", "grand_staircase", "kitchen", "dining_room"), monsters=("beast",), tokens=("victim", "feast", "cannibal"), hero_task="救出受害者", traitor_task="举行盛宴", hero_stat="might", hero_target=5, hero_progress_target="player_count", hero_detail="在阁楼救出受害者并向出口推进。", traitor_detail="推进盛宴轨道，每次代表消耗一名受害者。", monster_count="player_count"),
    47: dict(mode="worm_ouroboros", traitor_rule="revealer", hero_goal="在衔尾蛇蠕虫完全成长前杀死它。", traitor_goal="让蠕虫完成成长并杀死所有英雄。", rooms=("entrance_hall", "foyer", "grand_staircase", "basement_landing"), monsters=("giant",), tokens=("worm_head", "worm_body", "growth"), hero_task="斩杀衔尾蛇蠕虫", traitor_task="让蠕虫成长", hero_stat="might", hero_target=6, hero_progress_target=1, hero_detail="在蠕虫所在房间完成一次斩杀行动。", traitor_detail="推进蠕虫成长轨道。", monster_count=1, hero_win_target=1, traitor_win_type="track", traitor_progress_target=8),
    48: dict(mode="cursed_weapon", traitor_rule="revealer", hero_goal="找到被诅咒武器并用它永久杀死猩红杰克。", traitor_goal="让猩红杰克反复复活并杀死所有英雄。", rooms=("entrance_hall", "vault", "attic", "junk_room", "library"), monsters=("shadow",), tokens=("crimson_jack", "cursed_weapon", "weapon_cache"), hero_task="寻找诅咒武器", traitor_task="让猩红杰克复生", hero_stat="knowledge", hero_target=5, hero_progress_target=2, hero_detail="先搜索武器，再在猩红杰克所在房间完成永久击杀。", traitor_detail="推进复生轨道。", monster_count=1, hero_win_target=2),
    49: dict(mode="astral_spirit", traitor_rule="revealer", hero_goal="摧毁星界之灵并回到自己的肉身。", traitor_goal="占据英雄的肉身，或杀死所有英雄。", rooms=("chapel", "library", "pentagram_chamber", "bedroom", "master_bedroom"), monsters=("shadow",), tokens=("soul", "astral_spirit", "sanity_check", "knowledge_check"), hero_task="摧毁星界之灵", traitor_task="占据肉身", hero_stat=["sanity", "knowledge"], hero_target=5, hero_progress_target="player_count", hero_detail="完成精神或知识检定，逐步削弱星界之灵。", traitor_detail="推进附身轨道。", monster_count="player_count"),
    50: dict(mode="night_survival", traitor_rule="revealer", hero_goal="活到第十回合黎明，并让至少一名英雄存活。", traitor_goal="在第十回合前杀死所有英雄并继承遗产。", rooms=("entrance_hall", "foyer", "grand_staircase", "library", "chapel", "bedroom"), monsters=("beast", "cultist"), tokens=("servant", "dawn", "legacy"), hero_task="熬过黑夜", traitor_task="推进黑夜杀戮", hero_stat="might", hero_target=4, hero_progress_target=10, hero_win_type="turn_count", hero_win_target=10, hero_detail="存活并结束回合；黎明在第十回合到来。", traitor_detail="推进夜间威胁轨道。", monster_count="player_count"),
    51: dict(mode="darker_than_night", traitor_rule="revealer", hero_goal="完成驱魔，让房屋摆脱黑暗，或杀死叛徒。", traitor_goal="完成黑暗仪式，让房屋陷入黑暗。", rooms=("chapel", "library", "balcony", "garden", "graveyard", "patio", "tower"), monsters=("shadow",), tokens=("reflection", "darkness", "seal"), hero_task="封锁黑暗", traitor_task="完成黑暗仪式", hero_stat=["sanity", "knowledge"], hero_target=5, hero_progress_target="player_count", hero_detail="在驱魔来源处完成光明检定。", traitor_detail="推进黑暗仪式轨道。", monster_count="player_count", traitor_win_type="track", traitor_progress_target=6),
    52: dict(mode="ring_exorcism", traitor_rule="revealer", hero_goal="分解戒指并消灭房屋中的恶魔。", traitor_goal="保护戒指的魔法并杀死所有英雄。", rooms=("library", "chapel", "pentagram_chamber", "research_laboratory", "furnace_room"), monsters=("cultist",), tokens=("ring", "magic_dust", "demon", "antimagic"), hero_task="分解魔法戒指", traitor_task="守护戒指魔法", hero_stat="knowledge", hero_target=6, hero_progress_target=1, hero_detail="携带戒指在实验室、图书馆或小教堂完成分解。", traitor_detail="推进恶魔守护轨道。", monster_count="player_count", hero_win_target=1, required_cards=("omen_ring",), hero_requires=("omen_ring",)),
    53: dict(mode="toxic_object_escape", traitor_rule="revealer", hero_goal="至少一半英雄逃出前门，或清理死亡物体并保住至少一半英雄。", traitor_goal="阻止前门打开并让毒烟杀死英雄。", rooms=("entrance_hall", "foyer", "grand_staircase", "chapel", "kitchen", "larder"), monsters=("dog",), tokens=("toxic_object", "smoke", "barricade", "strength_check"), hero_task="打开前门并清理死亡物体", traitor_task="扩散毒烟", hero_stat=["might", "knowledge"], hero_target=5, hero_progress_target="half_players_ceil", hero_detail="在入口大厅清除路障，再带英雄逃离。", traitor_detail="推进毒烟扩散轨道。", monster_count=1, hero_win_target="half_players_ceil", engine_note="死亡物体的狗令牌使用狗模板；毒烟的跨房间伤害由房间效果层统一处理。"),
    54: dict(mode="arkanok_skull", traitor_rule="revealer", hero_goal="把阿卡诺克之颅送回其遗骸所在房间，打破死灵咒语。", traitor_goal="召唤阿卡诺克的幽灵，或杀死所有英雄。", rooms=("chapel", "crypt", "graveyard", "furnace_room", "bloody_room", "charred_room"), monsters=("zombie", "ghost"), tokens=("skull", "arkanok", "zombie", "sanity_check"), hero_task="归还阿卡诺克之颅", traitor_task="召唤阿卡诺克幽灵", hero_stat="knowledge", hero_target=5, hero_progress_target=1, hero_detail="携带颅骨在遗骸房间完成归还仪式。", traitor_detail="推进死灵召唤轨道。", monster_count="player_count", hero_win_target=1, required_cards=("omen_skull",), hero_requires=("omen_skull",)),
    55: dict(mode="kings_roads", traitor_rule="revealer", hero_goal="完成祛魅，关闭国王之路。", traitor_goal="让所有英雄被阴影附身或死亡。", rooms=("garden", "graveyard", "patio", "tower", "balcony", "underground_lake", "chapel", "library"), monsters=("shadow",), tokens=("shadow", "kings_road", "sanity_check", "knowledge_check"), hero_task="祛魅国王之路", traitor_task="让阴影附身英雄", hero_stat=["sanity", "knowledge"], hero_target=5, hero_progress_target="player_count", hero_detail="在国王之路入口或仪式房间完成祛魅检定。", traitor_detail="推进附身轨道。", monster_count="player_count"),
    56: dict(mode="time_sands", traitor_rule="revealer", hero_goal="击败叛徒并夺回时间之沙。", traitor_goal="保持对时间之沙的控制并杀死所有英雄。", rooms=("library", "attic", "entrance_hall", "foyer", "grand_staircase"), monsters=("shadow",), tokens=("time_sand", "memory_ghost", "time"), hero_task="夺回时间之沙", traitor_task="操纵时间", hero_stat="knowledge", hero_target=5, hero_progress_target=1, hero_detail="完成时间线索检定，最终击败叛徒。", traitor_detail="推进时间失控轨道。", monster_count="player_count", hero_win_target=1, traitor_win_type="track", traitor_progress_target=7),
    57: dict(mode="portrait_curse", traitor_rule="revealer", hero_goal="重新绘制肖像，打破肖像的保护诅咒。", traitor_goal="保护肖像并摧毁至少三件绘画，或杀死所有英雄。", rooms=("attic", "abandoned_room", "collapsed_room", "patio", "statuary_corridor", "larder", "crypt"), monsters=("shadow",), tokens=("painting", "portrait", "knowledge_check"), hero_task="重绘受诅咒肖像", traitor_task="保护并破坏画作", hero_stat="knowledge", hero_target=5, hero_progress_target="player_count", hero_detail="收集颜料，在肖像所在房间完成重绘。", traitor_detail="推进画作破坏轨道。", monster_count=1, hero_requires=()),
    58: dict(mode="nightfall_twilight", traitor_rule="revealer", hero_goal="摧毁所有噩梦或驱逐全部暮光。", traitor_goal="让暮光和噩梦吞没房屋，或杀死所有英雄。", rooms=("furnace_room", "garden", "graveyard", "patio", "balcony", "tower", "chapel", "library"), monsters=("shadow",), tokens=("nightmare", "torch", "twilight"), hero_task="驱散暮光与噩梦", traitor_task="扩大暮光", hero_stat="sanity", hero_target=5, hero_progress_target="player_count", hero_detail="在光照房间完成驱散行动。", traitor_detail="推进暮光覆盖轨道。", monster_count="player_count", traitor_win_type="track", traitor_progress_target=7),
    59: dict(mode="badge_curse", traitor_rule="revealer", hero_goal="把徽章挂到雕像上，打破女巫诅咒。", traitor_goal="把徽章从塔楼扔入地下湖摧毁，或杀死所有英雄。", rooms=("tower", "underground_lake", "statuary_corridor", "gallery", "chapel"), monsters=("witch",), tokens=("badge", "statue", "curse"), hero_task="把徽章挂上雕像", traitor_task="摧毁徽章", hero_stat=["knowledge", "might"], hero_target=5, hero_progress_target=1, hero_detail="携带徽章在雕像走廊完成悬挂仪式。", traitor_detail="推进徽章毁坏轨道。", monster_count=1, hero_win_target=1, required_cards=("item_amulet_of_the_ages",), hero_requires=()),
    60: dict(mode="sphinx_riddle", traitor_rule="revealer", hero_goal="解开古老谜语并阻止邪恶力量释放。", traitor_goal="先解开谜语释放力量，或杀死所有英雄。", rooms=("library", "research_laboratory", "pentagram_chamber", "crypt", "chapel"), monsters=("cultist",), tokens=("sphinx", "riddle", "might_check", "speed_check", "sanity_check"), hero_task="解开古老谜语", traitor_task="解开谜语释放力量", hero_stat="knowledge", hero_target=6, hero_progress_target=1, hero_detail="在图书馆、实验室或五芒星室完成谜语检定。", traitor_detail="推进谜语倒计时。", monster_count="player_count", hero_win_target=1, traitor_win_type="track", traitor_progress_target=1),
    61: dict(mode="ghost_warrior", traitor_rule="revealer", hero_goal="让幽灵战士安息。", traitor_goal="说服幽灵战士重新战斗，或杀死所有英雄。", rooms=("gallery", "graveyard", "wine_cellar", "chapel", "crypt"), monsters=("ghost",), tokens=("ghost_warrior", "statue", "sarcophagus", "armor", "shield"), hero_task="安抚幽灵战士", traitor_task="激励幽灵战士", hero_stat=["sanity", "knowledge"], hero_target=5, hero_progress_target=1, hero_detail="在雕像、墓地或石棺相关房间完成安抚。", traitor_detail="推进幽灵战士苏醒轨道。", monster_count="player_count", hero_win_target=1),
    62: dict(mode="bag_of_tricks", traitor_rule="revealer", hero_goal="利用四件纪念品的力量送走疯子并恢复房屋。", traitor_goal="收集四件纪念品，或杀死所有英雄。", rooms=("bloody_room", "larder", "crypt", "junk_room", "vault", "attic"), monsters=("madman",), tokens=("trinket", "madman", "speed_check", "sanity_check"), hero_task="利用纪念品送走疯子", traitor_task="收集纪念品", hero_stat=["speed", "sanity"], hero_target=4, hero_progress_target=1, hero_detail="在物品房间搜集纪念品并在疯子所在房间使用。", traitor_detail="每次成功搜索获得一件纪念品。", monster_count=1, hero_win_target=1),
    63: dict(mode="twisting_nether", traitor_rule="revealer", hero_goal="锚定足够多的房间，使房屋回到物质层。", traitor_goal="让房屋溶解进扭曲虚空，或杀死所有英雄。", rooms=("entrance_hall", "foyer", "grand_staircase", "upper_landing", "basement_landing", "chapel", "library"), monsters=("shadow",), tokens=("anchor", "astral_spirit", "void"), hero_task="锚定房间", traitor_task="溶解房间", hero_stat="knowledge", hero_target=5, hero_progress_target="player_count", hero_detail="在仍有未探索门口的房间完成锚定检定。", traitor_detail="推进虚空溶解轨道。", monster_count="player_count", traitor_win_type="track", traitor_progress_target=7),
    64: dict(mode="blood_offering", traitor_rule="revealer", hero_goal="救出女孩。", traitor_goal="让女孩被献祭，等待恶魔杀死叛徒和盟友。", rooms=("pentagram_chamber", "chapel", "crypt", "entrance_hall", "kitchen"), monsters=("cultist", "spider"), tokens=("girl", "cultist", "bat", "sacrifice"), hero_task="拯救女孩", traitor_task="完成血祭", hero_stat=["might", "knowledge"], hero_target=5, hero_progress_target=1, hero_detail="在女孩所在房间完成救援行动。", traitor_detail="推进血祭倒计时，达到阈值后恶魔介入。", monster_count="player_count", hero_win_target=1, traitor_win_type="track", traitor_progress_target=7),
    65: dict(mode="haunt_exorcism", traitor_rule="revealer", hero_goal="驱逐恶作剧者。", traitor_goal="让恶作剧者杀死所有英雄。", rooms=("junk_room", "larder", "attic", "library", "research_laboratory", "operating_laboratory", "chapel"), monsters=("ghost",), tokens=("haunt", "candle", "knowledge_check"), hero_task="驱逐恶作剧者", traitor_task="增强恶作剧者", hero_stat=["sanity", "knowledge"], hero_target=5, hero_progress_target="player_count", hero_detail="在指定房间完成驱魔检定。", traitor_detail="推进恶作剧者强度轨道。", monster_count=1),
    66: dict(mode="hell_on_earth", traitor_rule="revealer", hero_goal="在封闭房间用圣徽成功攻击并驱逐恶魔领主。", traitor_goal="让恶魔领主和叛徒杀死所有英雄。", rooms=("chapel", "library", "pentagram_chamber", "chasm", "crypt"), monsters=("giant", "cultist"), tokens=("demon_lord", "seal", "sanity_check", "power"), hero_task="为圣徽充能并驱逐恶魔", traitor_task="召集恶魔", hero_stat=["sanity", "knowledge"], hero_target=5, hero_progress_target=8, hero_detail="在小教堂、图书馆或圣徽所在房间完成充能，再进行驱逐。", traitor_detail="推进恶魔召集轨道。", monster_count="player_count", hero_win_target=8, required_cards=("omen_holy_symbol",)),
    67: dict(mode="storybook_twists", traitor_rule="revealer", hero_goal="完成与英雄人数相等的任务，并活到故事结束。", traitor_goal="让故事到达悲伤结局，或杀死所有英雄。", rooms=("library", "attic", "chapel", "garden", "tower", "pentagram_chamber"), monsters=("spider", "witch", "giant"), tokens=("story", "body", "twist", "witch", "dragon"), hero_task="完成故事任务", traitor_task="推动悲伤结局", hero_stat="knowledge", hero_target=5, hero_progress_target="player_count", hero_detail="完成当前章节所需任务；轨道推进由故事回合记录。", traitor_detail="推进故事章节和悲伤结局轨道。", monster_count=1, traitor_win_type="track", traitor_progress_target=7),
    68: dict(mode="labyrinth_escape", traitor_rule="revealer", hero_goal="收集钥匙、打开入口大厅前门并让至少一半英雄逃离迷宫。", traitor_goal="让迷宫自行封闭，或杀死超过一半英雄。", rooms=("entrance_hall", "catacombs", "mystic_elevator", "foyer", "grand_staircase", "upper_landing"), monsters=("cultist",), tokens=("key", "servant", "maze", "sanity_check"), hero_task="收集钥匙并逃离迷宫", traitor_task="封闭迷宫", hero_stat="knowledge", hero_target=5, hero_progress_target="half_players_floor", hero_detail="在入口大厅完成开门检定，再完成逃离行动。", traitor_detail="推进迷宫封闭轨道。", monster_count="player_count", hero_win_target="half_players_floor", traitor_win_type="track", traitor_progress_target=6),
    69: dict(mode="wisp_capture", traitor_rule="revealer", hero_goal="累计完成与英雄人数相等的捕捉检定，抓住小精灵。", traitor_goal="让小精灵坚持到逃脱轨道终点，或杀死所有英雄。", rooms=("entrance_hall", "foyer", "grand_staircase", "chapel", "library", "garden", "patio", "tower"), monsters=("ghost",), tokens=("wisp", "spore", "knowledge_check"), hero_task="捕捉小精灵", traitor_task="让小精灵逃走", hero_stat="knowledge", hero_target=4, hero_progress_target="player_count", hero_detail="与小精灵同房间时完成知识检定。", traitor_detail="推进小精灵逃脱轨道。", monster_count=1, traitor_win_type="track", traitor_progress_target=6),
    70: dict(mode="inhuman_transformation", traitor_rule="revealer", hero_goal="根据叛徒的怪物本性准备正确武器并击败他。", traitor_goal="完成吸血鬼、狼人或祸害蜘蛛的转变，或杀死所有英雄。", rooms=("crypt", "graveyard", "bloody_room", "balcony", "tower", "garden", "patio", "charred_room", "conservatory", "statuary_corridor", "mystic_elevator", "kitchen", "larder", "attic", "junk_room"), monsters=(), tokens=("bite", "holy_water", "silver_bullets", "bug_spray", "strength_check", "knowledge_check", "sanity_check"), hero_task="准备克制武器并阻止转变", traitor_task="完成怪物转变", hero_stat=["knowledge", "sanity"], hero_target=5, hero_progress_target=1, hero_detail="根据剧本提示制作圣水、银弹或杀虫剂，并在叛徒所在房间使用。", traitor_detail="访问转变所需房间并推进转变轨道。", monster_count=0, hero_win_target=1, traitor_win_type="track", traitor_progress_target=5, required_cards=("item_revolver", "item_axe", "item_blood_dagger")),
}


SUPPLEMENTAL_HAUNT_RULES: dict[int, dict[str, Any]] = {
    haunt_id: _make_scenario_rule(haunt_id, **definition)
    for haunt_id, definition in _SUPPLEMENTAL_SCENARIOS.items()
}


def get_haunt_rule_override(haunt_id: int) -> dict[str, Any]:
    """返回隐藏规则表；1-10 使用专属实现，11-70 使用逐号结构化规则。"""
    rule = HAUNT_RULE_OVERRIDES.get(haunt_id) or SUPPLEMENTAL_HAUNT_RULES.get(haunt_id, {})
    normalized = deepcopy(rule)
    if normalized:
        normalized.setdefault("version", 2)
        normalized.setdefault("status", "playable")
        normalized.setdefault(
            "win_conditions",
            [
                {
                    "winner": "heroes",
                    "type": "traitor_dead",
                    "reason": normalized.get("hero_goal", "叛徒已被击败。"),
                },
                {
                    "winner": "traitor",
                    "type": "all_heroes_dead",
                    "reason": normalized.get("traitor_goal", "所有英雄都倒下了。"),
                },
            ],
        )
    return normalized
