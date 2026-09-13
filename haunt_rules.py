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
        # p12："若「书」尚未进入游戏，则下一位发现带预兆符号房间的英雄应当搜索
        # 预兆牌堆并抽出它。"handler 的 on_room_discovered 只覆盖"作祟后新翻出
        # 预兆房"这一条路；实测 seed101/113 里触发作祟的那次发现发生在 handler
        # 生效之前，之后再无预兆房可翻，书整局没进场、英雄卡在第二步。
        # 官方引擎的通用搜牌通道（抽预兆时直接取走它）把这条路补全。
        "searchable_cards": ["omen_book"],
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
            # not_flag:bones_found 是必需的：找到骨头后这条行动若还留在
            # 可用列表里，机器人会站在原地反复"再找一次"而永不启程去墓地
            # （seed113/4p 实测 find_bones×239、骨头早已找到 300 回合不结束）。
            {"id": "find_bones", "side": "heroes", "stat": "knowledge", "target": 5, "rooms": ["attic", "bedroom", "master_bedroom"], "requires": ["flag:ghost_summoned", "flag:ghost_control=heroes", "not_flag:bones_found"], "set_flags": {"bones_found": True}},
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
            # same_room:frog 不可省：青蛙是"玩家身上的状态"，房间列表表达不了。
            # 缺它时机器人在没有青蛙的房间里也会反复尝试复原（seed109/4p 实测
            # restore_frog×104、原地往返 100 次），因为行动一执行它就当本回合
            # 完事、不再移动。
            {"id": "restore_frog", "side": "heroes", "stat": "knowledge", "target": 4, "requires": ["omen_book", "same_room:frog"]},
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
        # p15 原文："若「医疗包」卡尚未被发现，任何有机会抽物品卡的英雄都可以在
        # 牌堆中搜寻并直接取走医疗包，以代替正常抽牌。" 没有它，英雄的"毁卵"
        # 一步只能靠随机抽到医疗包——抽不到就永远打不出英雄胜利线。
        "searchable_cards": ["item_medical_kit"],
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
        # p17/p99：英雄胜利 = 杀死所有狼人（狗不必杀）。被咬转化的英雄 role 会
        # 改成 traitor（engine._haunt5_convert_to_werewolf），所以"场上没有存活
        # 的 traitor"恰好等价于"狼人全灭"。显式声明，不依赖隐藏默认。
        "win_conditions": [
            {"winner": "heroes", "type": "traitor_dead", "reason": "所有狼人都倒下了——诅咒终止在这一代。"},
            {"winner": "traitor", "type": "all_heroes_dead", "reason": "所有英雄或死或变，小屋外再没人记得他们。"},
        ],
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
            # id 必须与 engine._available_haunt5_actions / _perform_haunt5_action
            # 使用的 h5_ 前缀一致（这两条此前写成无前缀版本，成了永远不会被
            # 执行到的死数据——M10-15 测试扩容时补 5 号专项测试才发现）。
            {"id": "h5_find_revolver", "side": "heroes", "stat": "knowledge", "target": 5,
             "rooms": ["attic", "game_room", "junk_room", "master_bedroom", "vault"]},
            {"id": "h5_make_silver_bullets", "side": "heroes", "stat": "knowledge", "target": 5,
             "rooms": ["research_laboratory", "furnace_room"]},
            # 射杀狼人不生成行动对象：持左轮+银弹攻击狼人由通用攻击流程处理，
            # 这条声明只用于 required_cards 与寻路提示。
            {"id": "shoot_werewolf", "side": "heroes",
             "requires": ["item_revolver", "silver_bullets"], "attack": "speed", "kills": "werewolf"},
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
        #     免火，移动 -1，同房英雄也免火息）、矛（原版 p26 明确为
        #     "the Spear card"，即 omen_spear 预兆卡，与 19 号统一；
        #     摆在剩余的地下室房间供拾取；对龙攻击/防御 +4）
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
        "tokens": ["dragon", "antique_armor", "shield"],
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
            # set_flags 只在检定成功时被引擎应用——BugSprayMode 用它区分"这次真的配成了"
            # 与"执行过但知识 4+ 失败了"（_perform_generic_haunt_action 两种情况都返回 True）。
            {"id": "make_spray", "side": "heroes", "label": "调配杀虫剂", "detail": "在实验室或厨房集齐三枚配料（不拘谁拿着）后做知识 4+（p28）。", "stat": "knowledge", "target": 4, "rooms": ["research_laboratory", "kitchen"], "set_flags": {"spray_mixed": True}},
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
    19: {
        # 校准记录（2026-09-02，对照英雄手册 p30 / 叛徒手册 p101）：
        #   机制落在 BeastmasterMode：
        #   · 叛徒即驯兽师，持长矛（即 omen_spear 预兆卡，与剧本 15 统一）；
        #     五只动物随从按 p101 顺序布点（熊在任一其他
        #     探险者所在房间；狼进门厅，6 人局两只；鳄鱼进地下湖或地下室
        #     门厅；鼬进花园/墓地/阳台否则叛徒房间；鹰进阳台/塔楼/朝外窗
        #     房间，都没有则不出现）
        #   · 英雄胜：用力量攻击或持戒理智攻击对驯兽师造成 >2 点伤害并
        #     偷走长矛（引擎新钩子 special_steal；attack_attr_override
        #     扩展到玩家目标以支持持戒理智攻击）——驯兽师恢复神智
        #   · 杀死驯兽师 = 英雄失败（check_victory 显式判叛徒胜）
        #   · 动物随从被击败即杀死（非击晕）；熊主动攻击 +2、鳄鱼 +1
        #     （引擎读取 monster_specs 的 initiate_bonus，被攻击不加）
        #   简化：驯兽师开局的一次传送未实现（可选能力，bot 放弃）；
        #     长矛被偷后随从是否溃散原文未述，不影响胜负判定。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "beastmaster",
        "traitor_rule": "revealer",
        "hero_goal": "击败驯兽师并偷走长矛让他恢复神智——记住，杀了他你就输了。",
        "traitor_goal": "让动物随从吃掉所有英雄。",
        "suggested_monsters": ["beast", "wolf", "giant", "cat"],
        "required_cards": ["omen_ring"],
        "key_rooms": ["entrance_hall", "underground_lake", "basement_landing", "garden", "graveyard", "patio", "balcony", "tower"],
        "tokens": ["bear", "wolf", "crocodile", "weasel", "hawk"],
        "setup": {
            "tracks": {
                "minions_slain": {"label": "已斩杀的随从", "target": "player_count", "side": "heroes"},
            },
            "flags": {"spear_stolen": False, "beast_kind": {}},
        },
        "monsters": [
            {"template_id": "beast", "name": "熊", "spawn": "deferred", "speed": 3, "might": 5, "sanity": 4, "initiate_bonus": 2},
            {"template_id": "wolf", "name": "狼", "spawn": "deferred", "speed": 4, "might": 5, "sanity": 4},
            {"template_id": "giant", "name": "鳄鱼", "spawn": "deferred", "speed": 2, "might": 5, "sanity": 4, "initiate_bonus": 1},
            {"template_id": "cat", "name": "鼬", "spawn": "deferred", "speed": 5, "might": 2, "sanity": 6},
            {"template_id": "cat", "name": "鹰", "spawn": "deferred", "speed": 5, "might": 3, "sanity": 5},
        ],
        "actions": [],
        "win_conditions": [],
        "source_pages": [30, 101],
    },
    20: {
        # 校准记录（2026-09-02，对照英雄手册 p31 / 叛徒手册 p102）：
        #   机制落在 GhostBrideMode：
        #   · 教堂与地窖强制入场（p102）；新郎尸体令牌开局放地窖
        #   · 英雄四步（每步每回合一次，顺序由 requires_flags 串起）：
        #     ①知识5+（卧室/餐厅/图书馆或持书）得知新郎姓名 →
        #     ②知识4+（地窖）定位尸体 → ③力量4+（地窖）起尸（尸体令牌
        #     自动背上）→ ④背尸进教堂（入房按 2 格，可转交）+ 戒指进教堂
        #     → 新娘安息（英雄胜）
        #   · 新娘（ghost 模板承载）不可被任何手段伤害/击晕（p102，
        #     invulnerable，含戒指理智攻击——叛徒手册为准）；3-4 人局
        #     4/6，5-6 人局 5/7（handler 生成时按人数调整）
        #   · 新郎人选：优先持戒指的英雄，若其为女性则最年长男性；
        #     无男性英雄的 NPC 新郎分支未建模（本项目无性别数据，
        #     退化为任选一名英雄，已注明）
        #   · 新娘攻击：对非新郎正常精神伤害；对新郎转为力量流失
        #     （1-2→-1 / 3-4→-2 / 5+→-3），新郎力量耗尽死亡（掉戒指）
        #   · 婚礼：新郎死后新娘由 bot 移进教堂即开婚，叛徒回合推进
        #     计时，第 3 回合婚礼完成 → 叛徒胜
        #   简化：新娘穿墙移动近似为正常寻路；"新郎亡魂受叛徒控制"
        #     抽象为死亡离场；NPC 新郎分支未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "ghost_bride",
        "traitor_rule": "revealer",
        "hero_goal": "查明新郎姓名，从地窖起出尸体，把尸体和戒指带进教堂让新娘安息。",
        "traitor_goal": "让幽灵新娘杀死选定的新郎并把婚礼办完。",
        "suggested_monsters": ["ghost"],
        "required_cards": ["omen_ring"],
        "key_rooms": ["chapel", "crypt", "bedroom", "dining_room", "library"],
        "tokens": ["bride", "corpse"],
        "setup": {
            "tracks": {
                "wedding_timer": {"label": "婚礼计时", "target": 3, "side": "traitor"},
            },
            "flags": {
                "groom_name_known": False, "body_located": False, "body_disintered": False,
                "groom_id": None, "groom_dead": False, "wedding_started": False,
                "bride_room": None,
            },
        },
        "monsters": [
            {"template_id": "ghost", "name": "幽灵新娘", "spawn": "deferred", "speed": 4, "might": 0, "sanity": 6, "invulnerable": True},
        ],
        "actions": [
            {"id": "learn_name", "side": "heroes", "label": "查明新郎姓名", "detail": "在卧室/餐厅/图书馆做知识 5+，或持书检定（p31 第 1 步）。", "stat": "knowledge", "target": 5, "rooms": ["bedroom", "dining_room", "library"], "requires": [], "requires_flags": {"groom_name_known": False}, "set_flags": {"groom_name_known": True}},
            {"id": "learn_name_book", "side": "heroes", "label": "翻阅她的日记", "detail": "持古书做知识 5+，查明新郎姓名（p31 第 1 步）。", "stat": "knowledge", "target": 5, "requires": ["omen_book"], "requires_flags": {"groom_name_known": False}, "set_flags": {"groom_name_known": True}},
            {"id": "locate_body", "side": "heroes", "label": "定位尸体", "detail": "在地窖做知识 4+，找到真正新郎的埋骨处（p31 第 2 步）。", "stat": "knowledge", "target": 4, "rooms": ["crypt"], "requires_flags": {"groom_name_known": True, "body_located": False}, "set_flags": {"body_located": True}},
            {"id": "disinter_body", "side": "heroes", "label": "起出尸体", "detail": "在地窖做力量 4+，起出新郎的尸体并背上（p31 第 3 步）。", "stat": "might", "target": 4, "rooms": ["crypt"], "requires_flags": {"body_located": True, "body_disintered": False}, "set_flags": {"body_disintered": True}},
        ],
        "win_conditions": [],
        "source_pages": [31, 102],
    },
    21: {
        # 校准记录（2026-09-03，对照英雄手册 p32 / 叛徒手册 p103）：
        #   原文数值：僵尸 Speed 2 / Might 5 / Sanity 2；僵尸领主 Speed 3 / Might 7 / Sanity 2。
        #   领主改为"承受 7 点伤害才倒"（用回合/伤害轨记录，伤害不减属性）。
        #   英雄胜：摧毁领主 或 消灭所有僵尸；叛徒胜：所有英雄死亡。
        #   本次补齐（全部实现在 haunt_modes.ZombieLordMode）：
        #     · 免疫左轮（p32 "immune to the Revolver"）——顺带修好 content.py 里
        #       左轮缺少 speed 标签导致剧本 1/6 的 immune_to: ["speed"] 静默失效
        #     · 力量武器与炸药命中即杀死，徒手/其他属性只击晕（p32）
        #     · 圣徽：对持有者发动力量攻击的僵尸少掷两枚骰，领主不受影响（p32）
        #     · 只有持徽章者能伤到领主，且他不需要武器（p32）
        #     · 僵尸按 p103 的房间顺序布点（房不够则叠放，再给每间有僵尸的房补一只）
        #     · 叛徒开局即死并被领主令牌顶替；英雄被杀后转化为新僵尸
        #   已知简化（详见 handler 文档字符串）：转化后的僵尸由引擎/bot 代跑，
        #     不由原玩家操控；"抽物品时三选一放底"未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "zombie_lord",
        "traitor_rule": "revealer",
        "hero_goal": "摧毁僵尸领主，或把所有僵尸（包括被转化的同伴）全部消灭。",
        "traitor_goal": "僵尸群杀死所有英雄。",
        "suggested_monsters": ["zombie", "zombie_lord"],
        "required_cards": ["omen_medallion", "omen_holy_symbol"],
        "key_rooms": [],
        # 僵尸与领主都由怪物承载、领主伤害走轨道，本剧本没有需要 Token 对象的东西
        "tokens": [],
        "setup": {
            "tracks": {
                "lord_damage": {"label": "僵尸领主受到的伤害", "target": 7, "side": "heroes"},
            },
            "flags": {
                "zombies_placed": 0,
                "converted_ids": [],
            },
        },
        "monsters": [
            # spawn=deferred：布点由 handler 按 p103 的房间顺序自己算
            {"template_id": "zombie", "name": "僵尸", "spawn": "deferred",
             "speed": 2, "might": 5, "sanity": 2, "immune_to": ["speed"]},
            {"template_id": "zombie_lord", "name": "僵尸领主", "spawn": "haunt_room",
             "speed": 3, "might": 7, "sanity": 2, "damage_capacity": 7},
        ],
        # 英雄的目标就是战斗与找徽章，没有需要点击的剧本行动（同 10 号惯例）
        "actions": [],
        "win_conditions": [],
        "source_pages": [32, 103],
    },
    22: {
        # 校准记录（2026-09-03，对照英雄手册 p33 / 叛徒手册 p104）：
        #   驱魔竞赛：成功次数 = 玩家数；理智 5+（教堂/地窖/五芒星室/圣徽/戒指）、
        #     知识 5+（图书馆/研究实验室/古书/水晶球），每人每回合一次，
        #     每个来源只能成功用一次（与 8 号同一套底座，戒指替换灵应板）。
        #     检定令牌一旦放下就计入总数，来源随后塌掉也不作废（p33）。
        #   深渊起点：地下室里无人、带预兆或事件符号的房间；没有就从牌堆拿一间
        #     合法的地下室房放上（p104）。叛徒首个回合结束翻掉它，之后每个叛徒
        #     回合结束推进回合轨（从 1 开始）。
        #   坍塌速率（p104）：第 2 回合每人塌 1 间；第 3 回合掷 2 骰；第 4 回合 3 骰；
        #     第 5 回合起 4 骰。只能沿已有深渊的正交邻格扩散（不需要门、斜角不算）；
        #     整层塌完升到上一层，从"无人且留着未探索门口"的房间开始。
        #   房内有人：速度 4+ 逃进相邻、有门连通、已发现的房间，否则坠入深渊死亡。
        #   圣徽拖延：持圣徽且站在深渊邻格，可弃掉圣徽代替翻牌，并阻止坍塌到
        #     自己下个回合结束；回合轨照常推进。
        #   胜负：驱魔满员 → 英雄胜；英雄全灭 → 叛徒胜。叛徒被塌死也照常扩散（p104）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "abyss_exorcism",
        "traitor_rule": "revealer",
        "hero_goal": "在房子塌光之前完成与玩家数相等的驱魔检定。",
        "traitor_goal": "让深渊把整栋房子连同所有英雄一起吞掉。",
        "suggested_monsters": [],
        "required_cards": ["omen_holy_symbol", "omen_ring", "omen_book", "omen_crystal_ball"],
        "key_rooms": ["chapel", "crypt", "pentagram_chamber", "library", "research_laboratory"],
        "tokens": ["sanity_check", "knowledge_check"],
        "setup": {
            "tracks": {
                "exorcism_successes": {"label": "驱魔成功次数", "target": "player_count", "side": "heroes"},
                "abyss_turn": {"label": "深渊回合", "target": 5, "side": "traitor"},
            },
            "flags": {
                "used_exorcism_sources": [],
                "abyss_room": None,
                "abyss_started": False,
                "abyss_paused_until": 0,
            },
        },
        "monsters": [],
        "actions": [
            {"id": "chapel", "side": "heroes", "label": "在教堂驱魔", "detail": "理智检定 5+。教堂只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["chapel"], "progress": "exorcism_successes"},
            {"id": "crypt", "side": "heroes", "label": "在地窖驱魔", "detail": "理智检定 5+。地窖只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["crypt"], "progress": "exorcism_successes"},
            {"id": "pentagram_chamber", "side": "heroes", "label": "在五芒星室驱魔", "detail": "理智检定 5+。五芒星室只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["pentagram_chamber"], "progress": "exorcism_successes"},
            {"id": "omen_holy_symbol", "side": "heroes", "label": "借圣徽驱魔", "detail": "理智检定 5+。圣徽只能成功使用一次。", "stat": "sanity", "target": 5, "requires": ["omen_holy_symbol"], "progress": "exorcism_successes"},
            {"id": "omen_ring", "side": "heroes", "label": "借戒指驱魔", "detail": "理智检定 5+。戒指只能成功使用一次（p33 用戒指替换 8 号的灵应板）。", "stat": "sanity", "target": 5, "requires": ["omen_ring"], "progress": "exorcism_successes"},
            {"id": "library", "side": "heroes", "label": "在图书馆驱魔", "detail": "知识检定 5+。图书馆只能成功使用一次。", "stat": "knowledge", "target": 5, "rooms": ["library"], "progress": "exorcism_successes"},
            {"id": "research_laboratory", "side": "heroes", "label": "在研究实验室驱魔", "detail": "知识检定 5+。研究实验室只能成功使用一次。", "stat": "knowledge", "target": 5, "rooms": ["research_laboratory"], "progress": "exorcism_successes"},
            {"id": "omen_book", "side": "heroes", "label": "借古书驱魔", "detail": "知识检定 5+。古书只能成功使用一次。", "stat": "knowledge", "target": 5, "requires": ["omen_book"], "progress": "exorcism_successes"},
            {"id": "omen_crystal_ball", "side": "heroes", "label": "借水晶球驱魔", "detail": "知识检定 5+。水晶球只能成功使用一次。", "stat": "knowledge", "target": 5, "requires": ["omen_crystal_ball"], "progress": "exorcism_successes"},
            {"id": "sacrifice_holy_symbol", "side": "heroes", "label": "献出圣徽挡住深渊", "detail": "持圣徽且站在深渊邻格：弃掉圣徽代替翻牌，并阻止坍塌到自己下个回合结束（p33）。", "stat": "sanity", "target": 0, "requires": ["omen_holy_symbol"]},
        ],
        "win_conditions": [],
        "source_pages": [33, 104],
    },
    23: {
        # 校准记录（2026-09-03，对照英雄手册 p34 / 叛徒手册 p105）：
        #   骨架原本只丢了一只 giant 当怪物，与原版"根+尖端成对"的触手机制无关。
        #   尖端初始 Speed 2 / Might 3 / Sanity 6（p105 成长表第 0 回合），
        #   之后按回合成长：1-2 → 2/4/7，3-4 → 3/5/7，5-7 → 3/7/7，8+ → 4/8/8。
        #   根与尖端对数 = 玩家数，只能放在 熔炉房/温室/风琴房/地下湖/花园/裂隙
        #     （在场不够就从房间牌堆找出补齐，"You cannot save any tentacles for later"）；
        #     每扎一个根，同房间放一只尖端。根不能移动、不能攻击、也不能被攻击。
        #   头颅：持水晶球者做知识 4+ 凝视成功 → 掷 4 骰定头位
        #     （0 储藏室 / 1 厨房 / 2 风琴房 / 3 裂隙 / 4-5 地下湖 / 6 温室 / 7 地窖 / 8 熔炉房），
        #     球随即碎裂（弃掉）；该房未发现就从牌堆找出来交给叛徒接上合法楼层
        #     （地下湖必须放地下室）。
        #   杀头：走进头颅房间，用炸药或长矛攻击——不需要掷骰，自动杀死怪物，
        #     且不受炸药反噬伤害（p34）。
        #   被抓：尖端力量攻击击败英雄时不造成伤害，改为抓住并让其掉落所有物品；
        #     被抓者下个回合开始必须攻击它，打赢则获释但本回合之后每间房按 2 格计，
        #     打输或平手不掉血但本回合结束；抓着人的尖端不能攻击、每回合向配对的
        #     根移动 1 格；被抓者若在新回合开始时与根同房即被吞噬，该触手整株离场。
        #   尖端被任何攻击击败 → 放回配对的根所在房间并翻成昏迷面。
        #   铃铛对被抓者无效、灵应板对尖端无效（物品交互边界，未接）。
        #   叛徒开局即死并移出对局；英雄胜 = 摧毁头颅，叛徒胜 = 英雄全灭。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "tentacled_horror",
        "traitor_rule": "revealer",
        "hero_goal": "用水晶球找到触手怪的头颅，再带着炸药或长矛进房一击必杀。",
        "traitor_goal": "让触手把所有英雄拖回根部吃掉，或杀光他们。",
        "suggested_monsters": ["creeper_tip"],
        "required_cards": ["omen_crystal_ball", "item_dynamite", "omen_spear"],
        "key_rooms": ["furnace_room", "conservatory", "organ_room", "underground_lake", "garden", "chasm"],
        "tokens": ["root", "tip"],
        "setup": {
            "tracks": {
                "tentacle_turn": {"label": "触手成长回合", "target": 8, "side": "traitor"},
            },
            "flags": {
                "grabbed": {},
                "pairs_placed": 0,
                "head_found": False,
                "head_room": None,
                "creature_destroyed": False,
                "escaped_ids": [],
            },
        },
        "monsters": [
            # spawn=deferred：根与尖端成对入场，由 handler 按 p105 的房间表布置
            {"template_id": "creeper_tip", "name": "触手尖端", "spawn": "deferred",
             "speed": 2, "might": 3, "sanity": 6},
        ],
        "actions": [
            {"id": "gaze_crystal_ball", "side": "heroes", "label": "凝视水晶球找头位",
             "detail": "持水晶球做知识 4+（p34）。成功后掷 4 骰定位头颅，球随即碎裂。",
             "stat": "knowledge", "target": 4, "requires": ["omen_crystal_ball"],
             "requires_flags": {"head_found": False}},
            {"id": "destroy_head", "side": "heroes", "label": "用炸药或长矛摧毁头颅",
             "detail": "走进头颅所在房间，持炸药或长矛攻击——不掷骰，自动杀死怪物（p34）。",
             "stat": "knowledge", "target": 0,
             "requires_flags": {"head_found": True, "creature_destroyed": False}},
        ],
        "win_conditions": [],
        "source_pages": [34, 105],
    },
    24: {
        # 校准记录（2026-09-03，对照英雄手册 p35 / 叛徒手册 p106）：
        #   骨架原本用 spider 模板冒充蝙蝠，且没有"贴附吸血"这条核心机制。
        #   数值：蝙蝠 Speed 5 / Might 2 / Sanity 1（p106 页脚）。
        #   开局（p35/p106）：叛徒已死并移出对局；风琴房不在场就从牌堆找出来放上；
        #     取 24 枚蝙蝠令牌，塔楼或阁楼放 3 只、裂隙或地下墓穴放 3 只
        #     （两者都没发现就少放，p106 明文"the haunt begins with fewer Bats"）。
        #   入室（p106）：每个怪物回合掷「玩家数」枚骰，得到当回合进入的蝙蝠数；
        #     入口 = 塔楼/裂隙/温室/门厅/花园/墓地/露台/阳台（有朝外窗的房间），
        #     每个入口一次只进一只，蝙蝠多于入口才由叛徒选重复入口；
        #     进入算移动 1 格；场内蝙蝠总数封顶 24。
        #   攻击（p106）：蝙蝠不做普通攻击——每只贴脸掷 1 枚骰，掷出 2 就贴到该
        #     探险者身上；贴附后不再移动/攻击，宿主每回合开始按贴附数各受 1 点
        #     物理伤害（持盔甲少受 1 点），且每只贴附蝙蝠让宿主少走 1 格（至少 1 格）。
        #   英雄胜（p35 三步，每步每回合只能试一次）：① 风琴房力量 5+ 启动管风琴
        #     → ② 风琴房知识 6+ 奏出驱蝠之音，赶走所有未贴附的蝙蝠并封住入口
        #     → ③ 杀死仍贴在人身上的蝙蝠。力量攻击击败蝙蝠 = 杀死而非击晕。
        #   叛徒胜：所有英雄死亡。音乐爱好分支（知识 5+ 代替 6+）未建模——
        #     本仓库角色数据里没有爱好字段。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "bat_exodus",
        "traitor_rule": "revealer",
        "hero_goal": "在风琴房启动管风琴并奏出驱蝠之音封住入口，再杀死所有贴在人身上的蝙蝠。",
        "traitor_goal": "让蝙蝠群把每位探险者的血吸干。",
        "suggested_monsters": ["bat"],
        "required_cards": ["item_armor"],
        "key_rooms": ["organ_room"],
        "tokens": ["bat"],
        "setup": {
            "tracks": {
                "bats_released": {"label": "已入室的蝙蝠", "target": 24, "side": "traitor"},
            },
            "flags": {
                "organ_started": False,
                "bats_sealed": False,
                "attached": {},
                "last_entry_turn": -1,
            },
        },
        "monsters": [
            # spawn=deferred：开局布点与后续入室都由 handler 按 p106 规则处理
            {"template_id": "bat", "name": "蝙蝠", "spawn": "deferred",
             "speed": 5, "might": 2, "sanity": 1},
        ],
        "actions": [
            {"id": "start_organ", "side": "heroes", "label": "启动管风琴",
             "detail": "在风琴房做力量 5+ 启动管风琴（p35 第 1 步）。",
             "stat": "might", "target": 5, "rooms": ["organ_room"],
             "requires_flags": {"organ_started": False},
             "set_flags": {"organ_started": True}},
            {"id": "drive_away_bats", "side": "heroes", "label": "奏出驱蝠之音",
             "detail": "管风琴已启动后，在风琴房做知识 6+ 赶走所有未贴附的蝙蝠并封住入口（p35 第 2 步）。",
             "stat": "knowledge", "target": 6, "rooms": ["organ_room"],
             "requires_flags": {"organ_started": True, "bats_sealed": False}},
        ],
        "win_conditions": [],
        "source_pages": [35, 106],
    },
    25: {
        # 校准记录（2026-09-03，对照英雄手册 p36 / 叛徒手册 p107）：
        #   骨架原本只给了 cultist 怪与抽象进度轨道，与原版"巫毒娃娃"机制无关。
        #   核心机制：叛徒给每个英雄选一个娃娃（5 种，各绑定两个候选房间），
        #     在 p107 列出的两个候选房间里二选一放置；「恰有一间已发现」时必须
        #     选已发现的那间，两间都发现或都没发现时任选（bot 取列表第一间）。
        #     每个英雄会被宣读自己娃娃的描述引文（= 知道自己的娃娃类型与两个
        #     候选房间）。娃娃与房间模板绑定，候选房未上桌也算合法放置。
        #   探索规则变更（p36）：本剧本解除"进入带符号的新房间必须停"的限制——
        #     可以连续探索任意多新房间，只在"结束移动的房间"有符号时才抽牌；
        #     在当回合新发现的符号房间里搜寻娃娃也要抽一张符号牌。
        #     （引擎 hook：explore_stop_suspended + suppress_room_draw 延迟抽牌。）
        #   搜寻（p36）：知识 2+，每回合一次；成功后询问叛徒该房间是否有娃娃
        #     （电子版直接按盘面如实回答）。搜到的娃娃若属于自己→当场自动销毁；
        #     若属于别人→只公开位置（只有主人能安全销毁自己的娃娃）。
        #     搜寻落空（如实说"没有"）的结果对全桌公开（桌游里答案是口头的）。
        #   英雄死亡 → 该英雄的娃娃同时被销毁（p36）。
        #   时钟（p107）：叛徒回合结束时把回合/伤害轨道推进到下一数字（从 1 起），
        #     届时每个未销毁的娃娃影响其主人一次。叛徒死亡后按本仓库惯例改由
        #     "本轮最后一名存活玩家"的回合结束推进（原文未覆盖叛徒死亡）。
        #   效果（p107，回合数 = 轨道数字）：
        #     蜡娃娃  英雄自选失去 1 点力量或速度（bot 掉数值较高的一项，平手掉力量）；
        #     瓷娃娃  掷 4 枚骰，结果 < 回合数 → 娃娃坠落摔碎，英雄当场死亡；
        #     石娃娃  英雄做力量掷骰，结果 < 回合数 → 每项属性各失去 1 点；
        #     玻璃娃娃 英雄自选失去 1 点理智或知识（bot 同蜡娃娃策略）；
        #     布娃娃  英雄做知识掷骰，结果 < 回合数 → 受 2 点物理伤害。
        #   胜负（p36/p107）：英雄胜 = 销毁所有娃娃且存活英雄 ≥ 原英雄数的一半
        #     （向上取整）；叛徒胜 = 开局英雄过半死亡（严格大于一半）。两者互斥。
        #     叛徒死亡不等于英雄胜（覆盖引擎兜底；娃娃时钟继续走）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "voodoo_dolls",
        "traitor_rule": "revealer",
        "hero_goal": "循着线索找到每个巫毒娃娃的房间，销毁所有娃娃，并保证至少一半英雄活着。",
        "traitor_goal": "让娃娃的诅咒随着时间流逝杀死过半英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            "tracks": {
                # 回合/伤害轨道：p107 的 Turn/Damage Track，从 0 起每叛徒回合 +1
                "turn_damage": {"label": "回合/伤害轨道", "target": 0, "side": "traitor"},
            },
            "flags": {
                "dolls": [],
                "cleared_rooms": [],
            },
        },
        "monsters": [],
        "actions": [
            {"id": "search_doll", "side": "heroes", "label": "搜寻巫毒娃娃",
             "detail": "知识 2+（p36），每回合一次。成功后按盘面如实告知本房间有无娃娃；"
                       "搜到自己房间里的娃娃当场销毁，搜到别人的只公开位置。"
                       "在当回合新发现的符号房间里搜寻，须先抽一张符号牌。",
             "stat": "knowledge", "target": 2},
        ],
        "win_conditions": [],
        "source_pages": [36, 107],
    },
    26: {
        # 校准记录（2026-09-03，对照英雄手册 p37 / 叛徒手册 p108）：
        #   骨架原本用 spider 冒充老鼠 + 抽象进度轨道，与原版"鼠人仪式"无关。
        #   数值：老鼠 Speed 3 / Might 2 / Sanity 1（p108 页脚，新增 rat 模板）。
        #   开局（p37/p108）：叛徒（鼠人）仍在场；属性若低于初始值先恢复到
        #     初始值，然后每项属性 +1。在布置老鼠之前，先把身处五芒星室的
        #     探险者挪去一间邻格房间（不需要有门相连）。
        #   老鼠（p108）：数量 = 玩家数 × 2，放入有符号（事件/物品/预兆）的
        #     未被占据房间各一只；老鼠多于房间则叠放，少于则由叛徒任选
        #     （bot 按房间 key 序轮转，确定性）。另备 5 枚理智检定标记。
        #   老鼠规则（p108）：被击败即死亡（不会昏迷）；同房间多只老鼠可以
        #     合力攻击——力量相加对单一目标（最多 8 骰），合力攻击失败不受伤；
        #     单只攻击落败在引擎里按击晕表示（引擎不追踪怪物伤害，
        #     近似处理，见 handler 已知简化）。
        #   五芒星室（p37/p108）：叛徒在内时不受其他探险者任何影响；英雄与
        #     老鼠都不能进入（老鼠寻路绕开，英雄的移动选项与探索抽牌都会
        #     跳过它——探索抽到的五芒星室直接进弃牌堆换一张）。
        #   仪式（p108）：叛徒走到五芒星室，理智 3+ 每成功一次放 1 枚理智
        #     检定标记，并把一只"可用的"老鼠放到五芒星室邻格（不需要门；
        #     可用 = 初始 2×N 池里不在场的老鼠，即被杀死的会回流）。
        #     完成所需次数：3-4 人 5 次，5-6 人 4 次。
        #   胜负（p37/p108）：英雄胜 = 杀光所有老鼠，或在叛徒抵达五芒星室
        #     之前杀死叛徒；叛徒胜 = 完成仪式或杀死所有英雄。
        #     叛徒死亡≠英雄胜——必须是他还没进五芒星室时被杀（老坑 16 号吸收者）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "rat_ritual",
        "traitor_rule": "revealer",
        "hero_goal": "在鼠群的围攻下杀光屋里的每只老鼠；若叛徒还没进五芒星室，也可以直接杀了他。",
        "traitor_goal": "在五芒星室里完成邪恶的鼠类仪式，或杀光所有英雄。",
        "suggested_monsters": ["rat"],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            "tracks": {
                "ritual_rolls": {"label": "仪式理智检定", "target": 5, "side": "traitor"},
            },
            "flags": {
                "traitor_reached": False,
                "rats_placed": False,
                "rat_pool": 0,
            },
        },
        "monsters": [
            # spawn=deferred：开局布点与仪式回流都由 handler 按 p108 规则处理
            {"template_id": "rat", "name": "老鼠", "spawn": "deferred",
             "speed": 3, "might": 2, "sanity": 1},
        ],
        "actions": [
            {"id": "perform_ritual", "side": "traitor", "label": "进行鼠类仪式",
             "detail": "在五芒星室做理智 3+（p108）。成功放 1 枚理智检定标记，"
                       "并把一只可用的老鼠放到五芒星室邻格（不需要门）。"
                       "3-4 人需 5 次，5-6 人需 4 次。",
             "stat": "sanity", "target": 3, "rooms": ["pentagram_chamber"],
             "progress": "ritual_rolls"},
        ],
        "win_conditions": [],
        "source_pages": [37, 108],
    },
    27: {
        # 校准记录（2026-09-04，对照英雄手册 p38 / 叛徒手册 p109）：
        #   骨架原本用 plant 冒充怪物 + 抽象进度轨道，与原版"Blob 侵蚀"无关。
        #   Blob 不是怪物——是单团不断扩张的肉体，用房间集合（flags["blob_rooms"]）
        #     表示，令牌只是实体桌游的计数手段（≥20 枚），引擎不设上限。
        #   开局（p38/p109）：叛徒仍在场；持水晶球者弃掉它，Blob 从水晶球所在
        #     房间开始生长（没人持球时按叛徒所在房起算——校准回退，原文默认
        #     作祟由水晶球触发）。
        #   扩张（p109）：第一个怪物回合吞没起源房 + 门邻房；之后每个怪物回合
        #     沿门与楼梯/特殊链接扩散一圈（原文"用尽所有移动方式"；本仓库
        #     煤导槽/画廊/坍塌房无链接数据，慢速链接规则无法表达——校准简化，
        #     只按门与既有 links 扩散）。扩张完掷 1 骰，掷出 2 就再扩一圈，
        #     直到不是 2。
        #   转化（p109）：任何人在有 Blob 的房间里（含叛徒）立刻变成
        #     Blobperson——弃掉所有物品与预兆，速度 2，不能攻击/被攻击/抽牌/
        #     用神秘电梯/发现新房间，为叛徒而战。Blobperson 所占房间在怪物
        #     回合开始时种下新 Blob，与主体门连通后才从那里继续扩张
        #     （flags["blob_seeded"]，逐回合检查连通提升）。
        #   英雄流程（p38，每步每回合一次，全部知识 3+）：
        #     ① 检查弱点：站在与 Blob 房间门相连的邻室，成功 ×玩家数 → 弱点找到
        #        （知识检定令牌用完即重置，flags["weakness_found"] 置真）；
        #     ② 搜配料：弱点找到后，在 阁楼/温室/熔炉房/花园/图书馆/研究实验室/
        #        杂物间/厨房/储藏室/保险库/酒窖 检定；成功在身上放 1 份配料
        #        （每英雄分开计数），该房放理智标记且不可再搜（本仓库无独立
        #        Storeroom 模板，larder 兼任；保险库不建模"打开"状态）；
        #     ③ 投掷：在与 Blob 房间门相连的邻室用 1 格移动投出自己身上 1 份
        #        配料；投满玩家数份 → Blob 毁灭，英雄胜。
        #   胜负（p38/p109）：英雄胜 = 销毁 Blob；叛徒胜 = 所有英雄死亡或
        #     变成 Blobperson。叛徒死亡后 Blob 照常扩张（时钟改由本轮最后一名
        #     存活玩家代推），老坑 17 号吸收者。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "blob_weakness",
        "traitor_rule": "revealer",
        "hero_goal": "检查出 Blob 的弱点，找齐化学配料投进去，在所有人被同化之前毁掉它。",
        "traitor_goal": "让 Blob 吞没整栋房子——所有英雄死亡或变成 Blobperson。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            "tracks": {
                "knowledge_rolls": {"label": "弱点知识检定", "target": "player_count", "side": "heroes"},
                "blob_ingredients": {"label": "已投入的配料", "target": "player_count", "side": "heroes"},
            },
            "flags": {
                "weakness_found": False,
                "blob_origin": None,
                "blob_rooms": [],
                "blob_seeded": [],
                "blob_grew_once": False,
                "blobperson_ids": [],
                "ingredients": {},
                "searched_rooms": [],
            },
        },
        "monsters": [],
        "actions": [
            {"id": "examine_blob", "side": "heroes", "label": "检查 Blob 找弱点",
             "detail": "站在与 Blob 房间门相连的邻室做知识 3+（p38）。累计成功玩家数次"
                       "即找到弱点；每回合一次。",
             "stat": "knowledge", "target": 3, "progress": "knowledge_rolls",
             "requires_flags": {"weakness_found": False}},
            {"id": "search_ingredient", "side": "heroes", "label": "搜寻化学配料",
             "detail": "弱点找到后，在 阁楼/温室/熔炉房/花园/图书馆/研究实验室/杂物间/"
                       "厨房/储藏室/保险库/酒窖 做知识 3+（p38）。成功得 1 份配料，"
                       "该房放理智标记且不可再搜；每回合一次。",
             "stat": "knowledge", "target": 3, "rooms": ["attic", "conservatory", "furnace_room",
                       "garden", "library", "research_laboratory", "junk_room", "kitchen",
                       "larder", "vault", "wine_cellar"],
             "requires_flags": {"weakness_found": True}},
            {"id": "throw_ingredient", "side": "heroes", "label": "把配料投进 Blob",
             "detail": "在与 Blob 房间门相连的邻室，用 1 格移动投出自己身上的 1 份配料"
                       "（p38）。投满玩家数份 → Blob 销毁，英雄胜。每回合一次。",
             "stat": "knowledge", "target": 0},
        ],
        "win_conditions": [],
        "source_pages": [38, 109],
    },
    28: {
        # 校准记录（2026-09-04，对照英雄手册 p39 / 叛徒手册 p110）：
        #   骨架原本只有 giant 冒充怪 + 抽象"两次放逐"轨道，与原版无关。
        #   数值（p110 页脚）：恶魔一至五 速/力/智 = 2/5/5、3/4/4、4/3/3、
        #     5/2/2、6/1/1；恶魔领主 1/7/7。地狱门房放 领主 + 数量=英雄数的
        #     恶魔（按恶魔一、二…顺序）。
        #   地狱门（p110）：无人的事件符号房间，距最近探险者 ≥4 格；没有就
        #     选最远的（bot 按 (距离, key) 定序取最大）。
        #   戒指（p39）：作祟由所罗门戒指触发，揭示者（=叛徒）开局持有
        #     omen_ring。英雄胜利 = 持戒指击败恶魔领主两次（每次攻击可选
        #     力量或理智）；理智攻击对领主 +2；第一次击败击晕，第二次摧毁；
        #     领主攻击戒指持有人落败也算一次击败。
        #   策反（p39）：持戒指对普通恶魔的理智攻击成功 → 该恶魔被策反，
        #     由戒指持有人（电子版在其回合开始自动）移动并攻击其他恶魔或
        #     叛徒；戒指转给其他英雄则控制权随之转移；戒指被丢/被叛徒或
        #     恶魔拿走 → 恶魔恢复不受控。不持戒指击败恶魔 = 照常击晕。
        #   抢戒指（p110）：恶魔（含领主）击败戒指持有人且赢 2+ → 改为抢走
        #     戒指（不掉血）；恶魔不能使用/交易/丢掉戒指；击败该恶魔的
        #     探险者可取回戒指。
        #   限制（p110）：左轮等速度攻击对恶魔领主无效（monster_specs
        #     immune_to=["speed"]，复用引擎既有免疫）。
        #   胜负（p39/p110）：英雄胜 = 领主被戒指摧毁；叛徒胜 = 英雄全灭。
        #     叛徒死亡后恶魔照常追杀（怪物回合由本轮最后存活玩家代跑，
        #     老坑 18 号吸收者）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "demon_ring",
        "traitor_rule": "revealer",
        "hero_goal": "从叛徒手里拿到所罗门戒指，用它击败恶魔领主两次（理智攻击 +2）。",
        "traitor_goal": "让恶魔杀光所有英雄。",
        "suggested_monsters": ["demon_lord", "demon_1", "demon_2", "demon_3", "demon_4", "demon_5"],
        "required_cards": ["omen_ring"],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            "tracks": {
                "lord_defeats": {"label": "领主击败进度", "target": 2, "side": "heroes"},
            },
            "flags": {
                "portal_room": None,
                "lord_destroyed": False,
                "controlled_demons": [],
            },
        },
        "monsters": [
            # spawn=deferred：地狱门房由 handler 按 p110 规则选定并统一入场
            {"template_id": "demon_lord", "name": "恶魔领主", "spawn": "deferred",
             "speed": 1, "might": 7, "sanity": 7, "immune_to": ["speed"]},
            {"template_id": "demon_1", "name": "恶魔一", "spawn": "deferred",
             "speed": 2, "might": 5, "sanity": 5},
            {"template_id": "demon_2", "name": "恶魔二", "spawn": "deferred",
             "speed": 3, "might": 4, "sanity": 4},
            {"template_id": "demon_3", "name": "恶魔三", "spawn": "deferred",
             "speed": 4, "might": 3, "sanity": 3},
            {"template_id": "demon_4", "name": "恶魔四", "spawn": "deferred",
             "speed": 5, "might": 2, "sanity": 2},
            {"template_id": "demon_5", "name": "恶魔五", "spawn": "deferred",
             "speed": 6, "might": 1, "sanity": 1},
        ],
        "actions": [],
        "win_conditions": [],
        "source_pages": [39, 110],
    },
    29: {
        # 校准记录（2026-09-04，对照英雄手册 p40 / 叛徒手册 p111）：
        #   骨架原本用 giant 冒充怪物 + 抽象"火焰弱点"轨道，与原版无关。
        #   数值（p111 页脚）：弗兰肯斯坦怪物 Speed 3 / Might 8（无神智）。
        #   开局（p111）：怪物放在研究实验室或手术室；两间都不在场就从
        #     房间牌堆找出一间放上（本引擎按模板自身楼层放置，原文要求
        #     放上层——校准简化，见 handler 注释）。另备 5 枚火把令牌
        #     （原文"游戏过程中找火把没有次数限制"，引擎按无限池处理，
        #     只保留"每名探险者同时只能带 1 支"的限制）。
        #   怪物行为（p111）：全速扑向最近的可攻击英雄（引擎默认即如此）；
        #     攻击掷骰 +2（防守不加，走 monster_attack_roll_bonus）；
        #     免疫速度攻击（monster_specs immune_to=["speed"]，覆盖左轮
        #     等标了 speed 标签的武器；本仓库炸药未标 speed，按力量武器
        #     结算——校准简化）；赢 2+ 时可抢走并销毁英雄的火把而不掉血。
        #   英雄两种杀法（p40）：
        #     ① 火刑：在 烧焦的房间/熔炉房/五芒星室/厨房 点燃火把（同回合
        #        只能带一支）；在怪物所在房或门相连的邻室做速度攻击投掷——
        #        赢则怪物吃 1 次火把命中且英雄失去火把（不击晕），输则只是
        #        失去火把。命中次数 = 玩家数时怪物死亡。
        #     ② 推落：把怪物引到 塔楼/深渊，同房间做力量 6+ 推它坠亡。
        #   胜负（p40/p111）：英雄胜 = 怪物死亡（火把命中达标或推落成功）；
        #     叛徒胜 = 英雄全灭。叛徒死亡后怪物照常追杀（怪物回合由本轮
        #     最后存活玩家代跑，老坑 19 号吸收者）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "frankenstein_fire",
        "traitor_rule": "revealer",
        "hero_goal": "点燃火把投进怪物（命中玩家数次），或把它引到塔楼/深渊推下去。",
        "traitor_goal": "让力大无穷的怪物把所有英雄撕碎。",
        "suggested_monsters": ["frankenstein"],
        "required_cards": [],
        "key_rooms": [],
        "tokens": ["torch"],
        "setup": {
            "tracks": {
                "torch_hits": {"label": "火把命中", "target": "player_count", "side": "heroes"},
            },
            "flags": {
                "monster_destroyed": False,
            },
        },
        "monsters": [
            # spawn=deferred：由 handler 按 p111 放进实验室
            {"template_id": "frankenstein", "name": "弗兰肯斯坦的怪物", "spawn": "deferred",
             "speed": 3, "might": 8, "immune_to": ["speed"]},
        ],
        "actions": [
            {"id": "light_torch", "side": "heroes", "label": "点燃火把",
             "detail": "在烧焦的房间/熔炉房/五芒星室/厨房点燃一支火把（p40）。"
                       "每名探险者同时只能带 1 支，火把总数不限。",
             "stat": "knowledge", "target": 0,
             "rooms": ["charred_room", "furnace_room", "pentagram_chamber", "kitchen"]},
            {"id": "throw_torch", "side": "heroes", "label": "投掷火把",
             "detail": "在怪物所在房或门相连的邻室做速度攻击投掷（p40）。命中则怪物"
                       "吃 1 次火把（不击晕）并失去火把；落败也只是失去火把。",
             "stat": "knowledge", "target": 0},
            {"id": "push_monster", "side": "heroes", "label": "把怪物推下去",
             "detail": "怪物在塔楼或深渊时，同房间力量 6+ 把它推落摔死（p40）。",
             "stat": "knowledge", "target": 0, "rooms": ["tower", "chasm"]},
        ],
        "win_conditions": [],
        "source_pages": [40, 111],
    },
    30: {
        # 校准记录（2026-09-04，对照英雄手册 p41 / 叛徒手册 p112）：
        #   数值（p112 页脚）：德古拉 速 5/力 8/智 6；新娘 4/4/4
        #     （新增 dracula、bride 模板）。
        #   开局（p112）：叛徒变吸血鬼（每项属性 +1）；德古拉放在地窖或墓地
        #     （都不在场→无人房距最近探索者 ≥4 格，再不行就最远——同 28 号
        #     地狱门口径）；女孩卡弃掉，新娘放在叛徒房间；回合/伤害轨道置 0。
        #   时钟（p112）：叛徒回合开始把轨道推进到下一数字（从 1 起）；随后
        #     立即由其他探险者之一掷「玩家数」枚骰，结果 < 当前回合数 →
        #     日出（只发生一次）。
        #   日出后（p41）：每个叛徒回合开始，两只怪物吸血鬼每项属性各 -1
        #     （叛徒吸血鬼不弱化——原文只要求记录两只怪物的属性）；任一属性
        #     归零 → 昏迷不醒；英雄与昏迷吸血鬼同房间可自动钉杀（每回合一次，
        #     代替攻击）；吸血鬼进入/身处 阳台/温室/花园/墓地/庭院/塔楼
        #     （其它朝外窗未建模，同 24 号）立刻被阳光烧毁——叛徒吸血鬼同理。
        #   圣物准入（p112）：吸血鬼进教堂或持圣徽者的房间须理智 6+，失败
        #     不能进。两只怪物由 handler 接管移动逐房判定；叛徒吸血鬼按
        #     硬阻挡简化（原文可掷骰硬闯，电子版避免选项列表期掷骰）。
        #   魅惑（p112）：吸血鬼对异性目标可做理智攻击——电子版角色无性别
        #     字段，对所有目标可用（同 20 号口径）；可隔门从邻室发动；赢则
        #     目标改受等额速度伤害且可被拉进吸血鬼房间，输则吸血鬼不受伤。
        #     速度被魅惑打到见底 → 该角色变成吸血鬼（转投叛徒方：角色速度
        #     恢复初始值再各 +1，引擎 role 改为 traitor 以复用 bot 目标逻辑）。
        #   英雄杀法（p41）：长矛+力量攻击击败吸血鬼 = 钉杀（直接摧毁）；
        #     其它成功攻击照常造成伤害/击晕；持圣徽者击败吸血鬼后可按伤害
        #     点数把它沿门击退等距房间；与昏迷吸血鬼同房间可自动钉杀。
        #   胜负（p41/p112）：英雄胜 = 德古拉与新娘都被摧毁；叛徒胜 = 所有
        #     英雄死亡或变成吸血鬼。叛徒死亡后两只怪物照常行动（老坑 20 号
        #     吸收者）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "dracula_rising",
        "traitor_rule": "revealer",
        "hero_goal": "在日出削弱它们后，用长矛钉杀或阳光烧毁灭德古拉与新娘。",
        "traitor_goal": "让吸血鬼杀光所有英雄，或把他们全部变成吸血鬼。",
        "suggested_monsters": ["dracula", "bride"],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            "tracks": {
                "sun_track": {"label": "回合/伤害轨道", "target": 0, "side": "traitor"},
            },
            "flags": {
                "sunrise": False,
                "vampire_ids": [],
                "unconscious_ids": [],
                "dracula_destroyed": False,
                "bride_destroyed": False,
            },
        },
        "monsters": [
            # spawn=deferred：德古拉与新娘由 handler 按 p112 放置
            {"template_id": "dracula", "name": "德古拉伯爵", "spawn": "deferred",
             "speed": 5, "might": 8, "sanity": 6},
            {"template_id": "bride", "name": "新娘", "spawn": "deferred",
             "speed": 4, "might": 4, "sanity": 4},
        ],
        "actions": [
            {"id": "stake_unconscious", "side": "heroes", "label": "钉杀昏迷的吸血鬼",
             "detail": "与昏迷的吸血鬼同房间时，自动钉杀摧毁它（p41）。每回合一次，"
                       "代替攻击。",
             "stat": "knowledge", "target": 0},
        ],
        "win_conditions": [],
        "source_pages": [41, 112],
    },
    38: {
        # 校准记录（2026-09-04，对照英雄手册 p49 / 叛徒手册 p120）：
        #   机制落在 HellbeastMode（继承 ExorcismMode，与 22 号同一条继承路子；
        #   交接文档曾建议继承 24 号 BatSwarmMode，经原文核对是错的——火蝠不贴附
        #   英雄、不可被攻击、叛徒存活、伤害在怪物回合按房间区域结算，与 24 号
        #   几乎全相反；而驱魔来源清单与 22 号逐字一致，只把灵应板换成戒指）。
        #   火蝠 Speed 3、不可攻击也不可被攻击（invulnerable）；开局放「玩家数一半
        #     向上取整」只，全在作祟揭露房；不影响英雄移动（p49/p120）。
        #   怪物回合（叛徒存活，走引擎正常怪物回合=叛徒回合结束）：一次掷骰结果
        #     同时决定「现有火蝠移动格数」与「新进揭露房的火蝠数」，新蝠当回合
        #     不移动（先移动现有蝠→再繁殖→天然满足）。
        #   移动后：对每个「与≥1 英雄同房」的火蝠群掷「该房火蝠数」枚骰，房内所有
        #     英雄受该总和的物理伤害（盔甲「只防 1 点」由引擎既有盔甲语义近似承担，
        #     已知简化，同 24 号）。详见 haunt_modes.HellbeastMode 的已知简化清单。
        #   驱魔（英雄胜）复用 8/22 号底座：理智 5+（教堂/地窖/五芒星室/圣徽/戒指）
        #     或知识 5+（图书馆/研究实验室/古书/水晶球），每人每回合限一次，成功
        #     次数 = 玩家数，每个来源只能成功用一次（成功后作废，房间放检定令牌）。
        #   叛徒存活并操控火蝠（区别于 24 号叛徒开局即死）；无独立回合时钟。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "hellbeast_exorcism",
        "traitor_rule": "revealer",
        "hero_goal": "用不同的房间或物品完成等同玩家数的驱魔检定（理智/知识 5+），把火蝠赶出房屋。",
        "traitor_goal": "让火蝠把所有英雄烧死。",
        "suggested_monsters": ["bat"],
        "required_cards": ["omen_holy_symbol", "omen_ring", "omen_book", "omen_crystal_ball", "item_armor"],
        "key_rooms": ["chapel", "crypt", "pentagram_chamber", "library", "research_laboratory"],
        "tokens": ["sanity_check", "knowledge_check", "bat"],
        "setup": {
            "tracks": {
                "exorcism_successes": {"label": "驱魔成功次数", "target": "player_count", "side": "heroes"},
            },
            "flags": {"used_exorcism_sources": [], "haunt_room": "", "last_swarm_turn": -1},
        },
        "monsters": [
            # spawn=deferred：开局布点与每怪物回合繁殖都由 handler 按 p120 处理
            {"template_id": "bat", "name": "火蝠", "spawn": "deferred",
             "speed": 3, "might": 0, "sanity": 0, "invulnerable": True},
        ],
        # 九个驱魔行动：id 即来源名（房间用 rooms 限制、物品用 requires 限制），
        # 通用框架负责检定与进度；"同一来源只能成功一次"由 ExorcismMode
        # 按 used_exorcism_sources 过滤。22 号同款，戒指替换 8 号的灵应板。
        "actions": [
            {"id": "chapel", "side": "heroes", "label": "在教堂驱魔", "detail": "理智检定 5+。教堂只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["chapel"], "progress": "exorcism_successes"},
            {"id": "crypt", "side": "heroes", "label": "在地窖驱魔", "detail": "理智检定 5+。地窖只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["crypt"], "progress": "exorcism_successes"},
            {"id": "pentagram_chamber", "side": "heroes", "label": "在五芒星室驱魔", "detail": "理智检定 5+。五芒星室只能成功使用一次。", "stat": "sanity", "target": 5, "rooms": ["pentagram_chamber"], "progress": "exorcism_successes"},
            {"id": "omen_holy_symbol", "side": "heroes", "label": "借圣徽驱魔", "detail": "理智检定 5+。圣徽只能成功使用一次。", "stat": "sanity", "target": 5, "requires": ["omen_holy_symbol"], "progress": "exorcism_successes"},
            {"id": "omen_ring", "side": "heroes", "label": "借戒指驱魔", "detail": "理智检定 5+。戒指只能成功使用一次（p49 用戒指替换 8 号的灵应板）。", "stat": "sanity", "target": 5, "requires": ["omen_ring"], "progress": "exorcism_successes"},
            {"id": "library", "side": "heroes", "label": "在图书馆驱魔", "detail": "知识检定 5+。图书馆只能成功使用一次。", "stat": "knowledge", "target": 5, "rooms": ["library"], "progress": "exorcism_successes"},
            {"id": "research_laboratory", "side": "heroes", "label": "在研究实验室驱魔", "detail": "知识检定 5+。研究实验室只能成功使用一次。", "stat": "knowledge", "target": 5, "rooms": ["research_laboratory"], "progress": "exorcism_successes"},
            {"id": "omen_book", "side": "heroes", "label": "借古书驱魔", "detail": "知识检定 5+。古书只能成功使用一次。", "stat": "knowledge", "target": 5, "requires": ["omen_book"], "progress": "exorcism_successes"},
            {"id": "omen_crystal_ball", "side": "heroes", "label": "借水晶球驱魔", "detail": "知识检定 5+。水晶球只能成功使用一次。", "stat": "knowledge", "target": 5, "requires": ["omen_crystal_ball"], "progress": "exorcism_successes"},
        ],
        "win_conditions": [],
        "source_pages": [49, 120],
    },
    31: {
        # 校准记录（对照英雄手册 p42 / 叛徒手册 p113）：机制落在 haunt_modes.LivingHouseMode。
        #   六器官房（胃/肺/牙/腺体）在英雄“进入房间”或“开始回合”时查表结算；setup 时当前
        #   处于胃房间的英雄按 turn_order 立即各掷一次胃检定。
        #   心脏（organ_room，防御 Might 7）/大脑（attic，防御 Might 6，攻击前须先 Sanity 4+）
        #   建模为怪物：仅持 omen_spear 者可攻击，防御时不造成伤害，被长矛击败即“杀死房子”（英雄胜）；
        #   攻击心脏/大脑失败时，立即从屋内别处取一只抗体回流到该房。心脏/大脑永不移动/攻击。
        #   抗体（Speed 3 / Might 5 / Sanity 3，数量 = 英雄数）可穿墙移动。
        #   叛徒存活（traitor_rule=revealer），偷走长矛后在 chasm/furnace_room/underground_lake
        #   花一整回合扔掉即销毁长矛并获胜；无回合时钟/轨道。
        #   长矛来源原文未述——setup 授予 turn_order 中第一名英雄（解释性决策，见 handler docstring）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "living_house",
        "traitor_rule": "revealer",
        "hero_goal": "用长矛击败房屋的心脏（管风琴室）或大脑（阁楼），杀死这座活房子。",
        "traitor_goal": "让活房子消化杀死所有英雄，或夺走长矛并把它投入深渊/熔炉房/地下湖销毁。",
        "suggested_monsters": [],
        "required_cards": ["omen_spear"],
        "key_rooms": ["organ_room", "attic", "dining_room", "kitchen", "larder", "wine_cellar",
                       "conservatory", "balcony", "entrance_hall", "research_laboratory",
                       "operating_laboratory", "furnace_room", "underground_lake", "library", "chasm"],
        "tokens": ["heart", "brain", "stomach", "lungs", "teeth", "glands", "antibody"],
        "setup": {
            "tracks": {
                # 无自然回合时钟；house_slain 仅作“是否已用长矛杀死房子”的单格 UI 标记（0/1）。
                "house_slain": {"label": "杀死活房子", "target": 1, "side": "heroes"},
            },
            "flags": {"house_killed": False, "spear_destroyed": False},
        },
        "monsters": [
            # spawn=deferred：心脏/大脑/抗体的布点全部由 handler 在 setup 手动生成。
            {"template_id": "heart", "name": "心脏", "spawn": "deferred", "speed": 0, "might": 7, "sanity": 0, "controller": "traitor"},
            {"template_id": "brain", "name": "大脑", "spawn": "deferred", "speed": 0, "might": 6, "sanity": 0, "controller": "traitor"},
            {"template_id": "antibody", "name": "抗体", "spawn": "deferred", "speed": 3, "might": 5, "sanity": 3, "controller": "traitor"},
        ],
        # 英雄攻击心脏/大脑不设 rule_data action（它们是怪物，走引擎标准 attack 流，
        # 闸门由 handler 的 attack_allowed 施加）。只留叛徒的销毁长矛行动。
        "actions": [
            {"id": "throw_spear", "side": "traitor", "label": "把长矛投入深渊",
             "detail": "在深渊/熔炉房/地下湖花一整回合，把偷来的长矛销毁——叛徒直接获胜。",
             "rooms": ["chasm", "furnace_room", "underground_lake"], "requires": ["omen_spear"]},
        ],
        "win_conditions": [],
        "source_pages": [42, 113],
    },
    32: {
        # 校准记录（2026-09-05，对照英雄手册 p43 / 叛徒手册 p114）：
        #   骨架原本用 shadow 冒充怪物 + 抽象"维度锚点"轨道，与原版无关。
        #   开局（p114）：叛徒变节后房屋重排——已放置的非起始、非占用房间
        #     被撤下，与未抽房间牌、弃牌堆一起洗匀。本仓库**没有移除房间**
        #     的能力（22 号坍塌只是打标记不真删），撤房会破坏存档与寻路，
        #     故简化为"只洗匀房间牌堆与弃牌堆 + 日志还原氛围"，已知简化。
        #     风琴房按 _ensure_room_in_play 保证在场（原文：不在就从牌堆取
        #     出来接在起始房间旁）。
        #   毒大气（p43）：每个英雄回合开始掷 2 骰，从任意属性组合里扣减。
        #     人类逐点弹窗自选、bot 自动扣在离骷髅最远的属性上。
        #   回家（p43）：风琴房每回合可尝试一次知识检定，结果需达到
        #     3/4/5/6 人 → 15/16/18/20+。加值：场上每间预兆符号房 +1；
        #     图书馆乐谱/游戏室标本/塔楼星象三条线索各 +2（全局共享）；
        #     疯子或书在风琴房各 +2；音乐爱好 +2 因角色无 hobby 字段未建模
        #     （同 24 号口径）。
        #   干扰（p114）：叛徒在教堂/游戏室/两间实验室/五芒星室做知识 4+，
        #     每间成功放一枚 -3 令牌，每间限一枚。
        #   胜负（p43/p114）：英雄胜 = 风琴检定达标把房子送回原维度；
        #     叛徒胜 = 英雄全灭。叛徒死亡后毒大气照常生效（老坑 21 号吸收者）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "lost_dimension",
        "traitor_rule": "revealer",
        "hero_goal": "在风琴房弹对那首曲子，把整栋房子送回自己的维度。",
        "traitor_goal": "破坏传送器，或让异维度的大气杀死所有英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["organ_room"],
        "tokens": [],
        "setup": {
            "tracks": {
                "clues_found": {"label": "已找到的线索", "target": 3, "side": "heroes"},
                "sabotage": {"label": "传送器干扰", "target": 4, "side": "traitor"},
            },
            "flags": {
                "clue_books": False,
                "clue_trophy": False,
                "clue_stars": False,
                "sabotage_rooms": [],
                "returned_home": False,
            },
        },
        "monsters": [],
        "actions": [
            {"id": "play_organ", "side": "heroes", "label": "弹奏管风琴",
             "detail": "在风琴房做知识检定，结果需达到按人数定的门槛（3/4/5/6 人 → "
                       "15/16/18/20+），可叠加线索与房间加值、扣除叛徒干扰（p43）。"
                       "每回合一次。",
             "stat": "knowledge", "target": 0, "rooms": ["organ_room"]},
            {"id": "search_books", "side": "heroes", "label": "翻找乐谱",
             "detail": "在图书馆做知识 5+，找到乐谱后所有弹奏者 +2（p43）。"
                       "每条线索只能找到一次；每回合一次。",
             "stat": "knowledge", "target": 5, "rooms": ["library"],
             "requires_flags": {"clue_books": False}, "set_flags": {"clue_books": True},
             "progress": "clues_found"},
            {"id": "search_trophy", "side": "heroes", "label": "辨认标本",
             "detail": "在游戏室做理智 5+，认出异维度生物后所有弹奏者 +2（p43）。"
                       "每条线索只能找到一次；每回合一次。",
             "stat": "sanity", "target": 5, "rooms": ["game_room"],
             "requires_flags": {"clue_trophy": False}, "set_flags": {"clue_trophy": True},
             "progress": "clues_found"},
            {"id": "search_stars", "side": "heroes", "label": "观测星象",
             "detail": "在塔楼做知识 5+，凭星空定位家乡后所有弹奏者 +2（p43）。"
                       "每条线索只能找到一次；每回合一次。",
             "stat": "knowledge", "target": 5, "rooms": ["tower"],
             "requires_flags": {"clue_stars": False}, "set_flags": {"clue_stars": True},
             "progress": "clues_found"},
            {"id": "sabotage_transporter", "side": "traitor", "label": "改造传送器",
             "detail": "在教堂/游戏室/两间实验室/五芒星室做知识 4+，成功后在该房"
                       "放一枚干扰令牌：英雄的弹奏检定每枚 -3（p114）。每间限一枚。",
             "stat": "knowledge", "target": 4,
             "rooms": ["chapel", "game_room", "research_laboratory",
                       "operating_laboratory", "pentagram_chamber"]},
        ],
        "win_conditions": [],
        "source_pages": [43, 114],
    },
    33: {
        # 校准记录（2026-09-05，对照英雄手册 p44 / 叛徒手册 p115）：
        #   机制落在 LakeRescueMode：
        #   · 地下湖强制入场（_ensure_room_in_play，带门相邻地下室）
        #   · 房屋探索关闭：can_discover_rooms 只在"无任何已探明通路进
        #     地下室"时放行（地下室门厅开局已探明 → 整局关闭，与原文
        #     "unless there's no way into the basement" 一致）
        #   · 湖面砖：从地下湖两侧无门水缘按需铺设（extra_move_options
        #     追加 lake: 选项 → lake_move 铺面并移动），砖名"湖面"、
        #     面朝下（不触发符号抽牌）、四向互连；铺面从房间牌堆取砖，
        #     耗尽后取弃牌堆再取其他楼层（p44）
        #   · 游泳：回合开始在湖面砖上自动掷力量（4+ 每砖 2 格 /
        #     0-3 每砖 3 格），结果存 flags 供本回合移动费用下限
        #     （movement_cost_floor 新增 to_key 参数）
        #   · 搜索表（p115）：回合开始在湖面砖上掷 4 骰 + 距离加值
        #     （与地下湖间隔砖数含所在砖）+ 水晶球 +2 + 本回合新铺砖 +3，
        #     按表结算（19+ 救出女孩；10/17-18 湖怪 Might 5/6；14 触手
        #     Speed 5；12-13 大浪 Might 5+；6-7/15-16 理智 4+；11 累计 +3
        #     再掷；5 向深处挪 1 格再掷），迭代上限 8 段防死循环
        #   · 溺水：叛徒回合开始推进计时并掷等量骰，3-4 人局 10+ /
        #     5-6 人局 9+ 女孩溺亡 → 叛徒胜
        #   简化：湖面丢弃即沉没（on_item_dropped）；湖面死亡掉落也沉没
        #     未建模；女孩卡 set aside、属性微调未建模（同 16/18 号口径）；
        #     叛徒入湖可战不搜索（bot 自然满足）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "lake_rescue",
        "traitor_rule": "revealer",
        "hero_goal": "在女孩溺亡前划入湖面，顶住湖怪与幻象把她救上岸。",
        "traitor_goal": "让女孩溺亡，或让湖怪吃掉所有英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        # 机器人目标必须留空：地下湖靠门走不到（_path_length=9999），而
        # basement_landing 一旦作为常驻目标，会把英雄永久拽回岸上——
        # seed101/5p 实测："游出去又走回来"，400 回合不终局。下水方向改由
        # bot_ai 对"剧本给出的非棋盘目标（lake: 选项）"加分引导。
        "key_rooms": [],
        "tokens": ["lake_tile"],
        "setup": {
            "tracks": {
                "drown_timer": {"label": "溺水计时", "target": 20, "side": "traitor"},
            },
            "flags": {
                "girl_rescued": False, "girl_drowned": False,
                "swim_cost": {}, "drown_threshold": 10,
            },
        },
        "monsters": [],
        "actions": [],
        "win_conditions": [],
        "source_pages": [44, 115],
    },
    34: {
        # 校准记录（2026-09-05，对照英雄手册 p45 / 叛徒手册 p116）：
        #   机制落在 MadWorldMode：
        #   · 保险库强制入场（p45）；疯子卡归叛徒（p116 "Marc Antony"）
        #   · 随从（Servants）：数量 = 其他玩家数，每层一只+其余随机
        #     （spider 模板承载 3/3/1，engine_note 惯例）
        #   · 捕获：力量攻击击败随从/叛徒 → 选择抓住（不伤害不击晕）；
        #     背负者力量攻击 -2、入房 2 格、可转交；一次一人
        #   · 锁入：在保险库房间与被缚者同房花整回合 → 出局；
        #     入库后不可被营救
        #   · 营救：未被捕获的随从/叛徒以力量 2+ 胜过背负者 → 释放
        #   · 胜负：所有随从+叛徒均被锁入/杀灭 → 英雄胜；英雄全灭 → 叛徒胜
        #   简化：叛徒被杀即随从死亡未建模（原文只说 "kill or lock up the
        #     traitor"）；随从 bot 追最近英雄（引擎默认）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "mad_world",
        "traitor_rule": "revealer",
        "hero_goal": "抓住疯王与所有随从，把他们锁进保险库——背负时力量 -2、入房 2 格。",
        'traitor_goal': '让疯王与随从杀死所有元老院叛徒。',
        "suggested_monsters": ["spider"],
        "required_cards": [],
        "key_rooms": ["vault", "basement_landing"],
        "tokens": ["servant", "vault"],
        "setup": {
            "tracks": {
                "captives_locked": {"label": "已锁入保险库", "target": "player_count", "side": "heroes"},
            },
            "flags": {
                "captor": {}, "locked_up": [], "vault_open": False,
                "servants_killed": 0, "traitor_killed": False,
            },
        },
        "monsters": [
            {"template_id": "spider", "name": "疯人院随从", "spawn": "deferred", "count": "player_count", "speed": 3, "might": 3, "sanity": 1},
        ],
        "actions": [
            {"id": "lock_up", "side": "heroes", "label": "锁入保险库", "detail": "在保险库房间与被缚者同房花整回合，把TA锁进去（p45）。"},
            {"id": "pass_captive", "side": "heroes", "label": "转交俘虏", "detail": "把背着的俘虏交给同房间另一名英雄（p45）。"},
        ],
        "win_conditions": [],
        "source_pages": [45, 116],
    },
    35: {
        # 校准记录（2026-09-05，对照英雄手册 p46 / 叛徒手册 p117）：
        #   机制落在 SmallChangeMode：
        #   · 缩小：全员移动费用 ×2（movement_cost_multiplier 对所有
        #     角色返回 2，p46 "doorway counts as 2 spaces"）
        #   · 猫：3-4 人 1 只门厅 / 5-6 人 2 只（门厅+作祟房），
        #     Speed 6 / Might 7 / Sanity 5；猫力量胜利改为捕获（不伤害）
        #   · 捕获逃生：被俘者回合开始选属性对决，赢则自由；
        #     其他英雄击败猫 → 猫晕 + 释放
        #   · 玩具飞机：在卧室类房间知识 3+ 搜索 → 知识 4+ 发动 →
        #     速度 5 移动 → 通过外缘房间逃离（至少半数英雄出逃）
        #   · 猫拍落飞机：猫 Speed 7+ / 叛徒 Speed 5+
        #   简化：楼梯 Might 3+ / 不可用电梯/塌房/画廊等缩小限制未建模
        #     （can_discover_rooms 与 movement 层不区分楼梯与门）；
        #     叛徒不可直接攻击英雄（p117）——attack_allowed 返回 False；
        #     飞机搭乘/接送/坠机等细节简化为"发动后在外缘房间逃离"。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "small_change_escape",
        "traitor_rule": "revealer",
        "hero_goal": "找到玩具飞机，让至少半数英雄从外缘房间乘机逃离。",
        "traitor_goal": "让猫吃掉超过半数的英雄。",
        "suggested_monsters": ["cat"],
        "required_cards": [],
        "key_rooms": ["entrance_hall", "bedroom", "master_bedroom", "attic", "garden", "graveyard", "patio", "tower"],
        "tokens": ["toy_airplane", "cat"],
        "setup": {
            "tracks": {
                "heroes_escaped": {"label": "已逃离英雄", "target": "half_players_ceil", "side": "heroes"},
            },
            "flags": {
                "plane_found": False, "plane_started": False,
                "captured": {}, "escaped": [],
            },
        },
        "monsters": [
            {"template_id": "cat", "name": "猫", "spawn": "deferred", "count": 1, "speed": 6, "might": 7, "sanity": 5},
        ],
        "actions": [
            {"id": "search_plane", "side": "heroes", "label": "搜索玩具飞机", "detail": "在卧室类房间做知识 3+（p46）。", "stat": "knowledge", "target": 3, "rooms": ["bedroom", "master_bedroom", "larder", "attic", "game_room"], "requires_flags": {"plane_found": False}, "set_flags": {"plane_found": True}},
            {"id": "start_plane", "side": "heroes", "label": "发动飞机", "detail": "在同房间做知识 4+ 发动玩具飞机（p46）。", "stat": "knowledge", "target": 4, "requires": [], "requires_flags": {"plane_found": True, "plane_started": False}, "set_flags": {"plane_started": True}},
            {"id": "escape_plane", "side": "heroes", "label": "乘机逃离", "detail": "在飞机已发动的状态下从外缘房间逃出（p46）。", "requires_flags": {"plane_started": True}},
        ],
        "win_conditions": [],
        "source_pages": [46, 117],
    },
    36: {
        # 校准记录（2026-09-05，对照英雄手册 p47 / 叛徒手册 p118）：
        #   机制落在 SwampEscapeMode：
        #   · 阁楼强制入场；小艇在阁楼（p118）；背负 ×2 移动、可交易
        #   · 洪水：叛徒回合结束推进；1-6 回合六个阶段（地下室部分淹
        #     → 全淹 → 一楼部分淹 → 全淹 → 全屋部分淹 → 全屋全淹）
        #     部分淹 -2 移动 / 全淹 -4 移动 + 2 骰物理（不可防）；叛徒免疫
        #   · 逃跑：全部活英雄在阳台/塔楼+小艇 → 逃离（至少半数出逃）
        #   · 勋章：部分/全淹房间丢弃勋章暂停洪水一回合（弃卡）
        #   · 破坏小艇：叛徒力量 3+ 攻击小艇，5 次毁坏 → 叛徒胜
        #   简化：狗不能背小艇未建模（狗令牌本 haunt 不出现）；洪水
        #     移动减值用 movement_cost_floor 近似（不叠加怪物费）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "swamp_escape",
        "traitor_rule": "revealer",
        "hero_goal": "在房子沉没前把小艇扛到阳台或塔楼，全员乘艇逃离。",
        "traitor_goal": "毁掉小艇或让超过半数英雄淹死。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["attic", "balcony", "tower", "basement_landing"],
        "tokens": ["rowboat"],
        "setup": {
            "tracks": {
                "flood_timer": {"label": "洪水计时", "target": 6, "side": "traitor"},
                "boat_damage": {"label": "小艇受损", "target": 5, "side": "traitor"},
            },
            "flags": {
                "boat_destroyed": False, "medallion_pause": False,
                "boat_carrier": None,
            },
        },
        "monsters": [],
        "actions": [
            {"id": "take_rowboat", "side": "heroes", "label": "扛起小艇", "detail": "在阁楼拿起小艇（p47）。", "rooms": ["attic"], "requires_flags": {"boat_destroyed": False}},
            {"id": "drop_medallion", "side": "heroes", "label": "投掷勋章", "detail": "在部分/全淹的房间丢弃勋章暂停洪水一回合（p47）。", "requires": ["omen_medallion"]},
            {"id": "escape_boat", "side": "heroes", "label": "乘艇逃离", "detail": "全部活英雄在小艇所在的外缘房间时逃离（p47）。", "requires_flags": {"boat_destroyed": False}},
        ],
        "win_conditions": [],
        "source_pages": [47, 118],
    },
    37: {
        # 校准记录（2026-09-05，对照英雄手册 p48 / 叛徒手册 p119）：
        #   机制落在 DeathCheckmateMode：
        #   · 死神（shadow 模板承载）不可被攻击/影响（invulnerable）；
        #     放在有英雄的房间
        #   · 国际象棋：死神回合开始，同房知识最高英雄 vs 死神（知识 8、
        #     空白骰重掷一次）；英雄知识 > 死神 → 将军（英雄胜）
        #   · 圣印：5 枚（保险库/地窖/实验室/手术室/游戏室），理智 4+
        #     破解 → 死神掷骰 -1（3-4 人局 -2）
        #   · 古书：持有者知识检定 +1 骰（上限 8）
        #   · 死神赢 1-2 → 全英雄 -1 理智；3-4 → -1 力量；5+ → -1 理智-1 力量
        #   · 弃赛：死神房间无英雄 → 叛徒胜
        #   简化：叛徒不可进死神房间/不可用铃/枪/炸药未在引擎层拦截
        #     （bot 自然不会）；死神空白骰重掷用 monster_rerolls_blanks。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "death_checkmate",
        "traitor_rule": "revealer",
        "hero_goal": "破解圣印削弱死神，在知识对弈中将军死神。",
        "traitor_goal": "让死神耗死所有英雄，或让他们弃赛。",
        "suggested_monsters": ["shadow"],
        "required_cards": [],
        "key_rooms": ["vault", "crypt", "research_laboratory", "operating_laboratory", "game_room"],
        "tokens": ["death_token", "holy_seal"],
        "setup": {
            "tracks": {
                "seals_broken": {"label": "已破解圣印", "target": 5, "side": "heroes"},
            },
            "flags": {
                "seals_broken": 0, "death_dice_reduction": 0,
                "groom_name_known": False,
            },
        },
        "monsters": [
            {"template_id": "shadow", "name": "死神", "spawn": "haunt_room", "count": 1, "speed": 0, "might": 0, "sanity": 0, "invulnerable": True},
        ],
        "actions": [
            {"id": "break_seal", "side": "heroes", "label": "破解圣印", "detail": "理智 4+ 破解一枚圣印，死神掷骰减少（p48）。", "stat": "sanity", "target": 4},
        ],
        "win_conditions": [],
        "source_pages": [48, 119],
    },
    39: {
        # 校准记录（2026-09-05，对照英雄手册 p50 / 叛徒手册 p121）：
        #   机制落在 HeirAssassinMode：
        #   · 雕像走廊强制入场；王座在雕像走廊
        #   · 继承人：揭示者秘密选择（bot 随机选一名非自己英雄），
        #     身份存 flags（联机隐藏信息裁剪之外的秘密）
        #   · 刺客：数量=玩家数，隐藏在已探明空房（每房至多一只），
        #     英雄进入即暴露并 sneak attack（Might 2，无防御），攻击后服毒死亡
        #   · 计时：叛徒回合结束推进；第 3/6 回合各补一批新刺客
        #   · 胜利：继承人在雕像走廊持矛+戒指 → 英雄胜；继承人死 → 叛徒胜
        #   简化：叛徒不知道继承人是谁（bot 也不针对性攻击）；
        #     继承人死亡的"诚实回答"机制不需要（bot 直接查 flags）。
        #   M10-35 修：矛改用项目已有的 omen_spear 卡（p50 原文就是
        #     "the Spear card"）放进随机已探明房间——旧版用 marker 令牌，
        #     而引擎没有令牌拾取机制，继承人永远拿不到矛 = 英雄线不可达。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "secret_heir",
        "traitor_rule": "revealer",
        "hero_goal": "保护继承人，让TA拿着矛与戒指登上雕像走廊的王座。",
        "traitor_goal": "让隐藏的刺客杀死继承人。",
        "suggested_monsters": [],
        # 矛与戒指都必须交到继承人手上（quest_carrier 钩子 + bot 寻路目标）。
        "required_cards": ["omen_spear", "omen_ring"],
        # 机器人目标必须留空：继承人的目标随"手里缺哪件、东西在谁手上"变化，
        # 静态 key_rooms（原来是 statue 走廊 + 地下室平台）与真实目标同档竞争，
        # 会让继承人在楼上楼下反复横跳（seed101/5p 实测 400 回合不终局）。
        # 全部交给 HeirAssassinMode.bot_goal_rooms 动态给出。
        "key_rooms": [],
        "tokens": ["spear", "assassin"],
        "setup": {
            "tracks": {
                "assassin_timer": {"label": "刺客计时", "target": 6, "side": "traitor"},
            },
            "flags": {
                "heir_id": None, "assassin_rooms": [], "spear_room": None,
            },
        },
        "monsters": [
            {"template_id": "cultist", "name": "刺客", "spawn": "deferred", "count": "player_count", "speed": 3, "might": 2, "sanity": 2},
        ],
        "actions": [],
        "win_conditions": [],
        "source_pages": [50, 121],
    },
    40: {
        # 校准记录（2026-09-05，初版；2026-09-12 M10-35 补齐实现）：
        #   机制落在 BuriedAliveMode：
        #   · 埋人：叛徒在"作祟前已发现的地下室房间"里秘密选一间（不足 5 间
        #     先补地下室房间，含楼梯平台）
        #   · 计时：叛徒回合结束轨位 +1，掷等于轨位的骰子，被埋者累计伤害；
        #     12 点死亡 → 叛徒胜
        #   · 搜查：英雄在地下室房间知识 3+ → 找到/排除埋葬室
        #   · 挖掘：埋葬室内力量 4+，进度 = 开局玩家人数 → 英雄胜
        #   · 通灵板：理智 7+ 得知埋葬室；5-6 回复 2 骰伤害
        #   旧版（M7 批次）是 stub：只有"英雄全灭→叛徒胜"，英雄唯一的胜利
        #   路径是杀叛徒后落引擎兜底——与 p51 完全不符，M10-35 补齐。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "buried_alive",
        "traitor_rule": "revealer",
        "hero_goal": "在地下室找到埋葬室，挖出被活埋的朋友。",
        "traitor_goal": "让被埋的人在泥土下死去。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            "tracks": {
                "burial_damage": {"label": "被埋朋友的伤害（12 点死亡）", "target": 12, "side": "traitor"},
                "dig_progress": {"label": "挖出朋友", "target": "player_count", "side": "heroes"},
            },
            "flags": {},
        },
        "monsters": [],
        "actions": [],
        "win_conditions": [
            {"winner": "traitor", "type": "all_heroes_dead", "reason": "所有英雄都被活埋了。"}
        ],
        "source_pages": [51, 122],
    },
    41: {
        # 校准记录（2026-09-05，对照英雄手册 p52 / 叛徒手册 p123）：
        #   机制落在 InvisibleTraitorMode：
        #   · 隐形：叛徒不可见（bot 局仍追击；sneak attack 无防御，
        #     骰数 = ceil(原始英雄数/2)）
        #   · 侦测：被偷袭幸存后知识 3+ 探知叛徒所在房间
        #   · 胜利：叛徒死亡 → 英雄胜
        #   简化：叛徒攻击仍走引擎攻击流程（不做无防御 FlatDamage——
        #     引擎 player-vs-player 攻击不可 hook 伤害公式）；骷髅/灵应板
        #     追踪/偷窃未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "invisible_traitor",
        "traitor_rule": "revealer",
        "hero_goal": "侦测隐形叛徒的踪迹，在TA杀死你们之前反杀。",
        "traitor_goal": "在隐身状态下杀死所有英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            "tracks": {"detections": {"label": "侦测次数", "target": 10, "side": "heroes"}},
            "flags": {"detected_by": []},
        },
        "monsters": [],
        "actions": [
            {"id": "detect_traitor", "side": "heroes", "label": "侦测叛徒", "detail": "知识 3+ 探知叛徒所在房间（p52）。", "stat": "knowledge", "target": 3},
        ],
        "win_conditions": [
            {"winner": "heroes", "type": "traitor_dead", "reason": "隐形叛徒被反杀了。"}
        ],
        "source_pages": [52, 123],
    },
    42: {
        # 校准记录（2026-09-05，对照英雄手册 p53 / 叛徒手册 p124）：
        #   骨架 rule_data 已足够（hell_gate_hero 模式），核心机制是
        #   "英雄变成英雄怪物"——需要英雄转怪物的深层引擎支持。
        #   留为 fidelity=skeleton + generic 兜底，M8 批次专项精修。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "hell_gate_hero",
        "traitor_rule": "revealer",
        "hero_goal": "阻止地狱之门打开。",
        "traitor_goal": "打开地狱之门。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {"tracks": {"progress": {"label": "进度", "target": 10, "side": "heroes"}}, "flags": {}},
        "monsters": [],
        "actions": [
            {"id": "animate_statue", "side": "heroes", "label": "激活雕像", "detail": "把一件物品放进雕像手中（p53）。圣徽→审判官/斧→战士/水晶球→先知/古书→巫师。"},
            {"id": "move_statue", "side": "heroes", "label": "移动雕像", "detail": "知识或理智检定移动雕像（格数=结果）（p53）。"},
        ],
        "win_conditions": [{"winner": "traitor", "type": "all_heroes_dead", "reason": "所有英雄都死了。"}],
        "source_pages": [53, 124],
    },
    43: {
        # 校准记录（2026-09-05，对照英雄手册 p54 / 叛徒手册 p125）：
        #   骨架 rule_data 已足够（shadow_exorcism 模式），核心机制是
        #   "影子分身逐个击破"——需要影子分裂机制。
        #   留为 fidelity=skeleton + generic 兜底，M8 批次专项精修。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "shadow_exorcism",
        "traitor_rule": "revealer",
        "hero_goal": "在影子分身杀死你们之前驱逐它们。",
        "traitor_goal": "让影子分身吃掉所有英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["pentagram_chamber", "catacombs", "chapel", "library", "research_laboratory", "balcony", "garden", "graveyard", "patio", "tower"],
        "tokens": [],
        "setup": {"tracks": {"progress": {"label": "进度", "target": 10, "side": "heroes"}}, "flags": {"ritual_found": False, "shadow_bound": {}, "pentagram_reached": []}},
        "monsters": [{"template_id": "ghost", "name": "影子", "spawn": "deferred", "count": "player_count", "speed": 3, "might": 0, "sanity": 0, "invulnerable": False}],
        "actions": [
            {"id": "find_ritual", "side": "heroes", "label": "寻找仪式", "detail": "在地窖/教堂/图书馆/实验室做知识 4+（p54）。", "stat": "knowledge", "target": 4, "rooms": ["catacombs", "chapel", "library", "research_laboratory"], "requires_flags": {"ritual_found": False}, "set_flags": {"ritual_found": True}},
            {"id": "ritual_roll", "side": "heroes", "label": "仪式检定", "detail": "在外缘房间做知识/理智 5+，放一枚仪式令牌（p54）。", "stat": ["knowledge", "sanity"], "target": 5, "rooms": ["balcony", "garden", "graveyard", "patio", "tower"], "requires_flags": {"ritual_found": True}, "progress": "ritual_progress"},
        ],
        "win_conditions": [],
        "source_pages": [54, 125],
    },    44: {
        # 校准记录（2026-09-05）：简化实现
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "supernatural_aging",
        "traitor_rule": "revealer",
        "hero_goal": "阻止超自然衰老。",
        "traitor_goal": "衰老：每回合掷骰老化，完成复活仪式停止。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["catacombs", "charred_room", "crypt", "gallery", "kitchen", "pentagram_chamber", "tower"],
        "tokens": [],
        "setup": {
            "tracks": {"ritual_progress": {"label": "复活仪式", "target": "player_count", "side": "heroes"}},
            "flags": {"aging_tokens": {}, "ritual_rooms_used": []},
        },
        "monsters": [],
        "actions": [
            {"id": "ritual_roll", "side": "heroes", "label": "仪式检定", "detail": "在仪式房间做理智/知识 5+（p55）。", "stat": ["sanity", "knowledge"], "target": 5, "progress": "ritual_progress"},
        ],
        "win_conditions": [
            {"winner": "traitor", "type": "all_heroes_dead", "reason": "所有英雄都死了。"}
        ],
        "source_pages": [55, 126],
    },
    45: {
        # 校准记录（2026-09-05）：骨架 + generic 兜底（M8/M9 批次专项精修）
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "time_bomb",
        "traitor_rule": "revealer",
        "hero_goal": "拆除定时炸弹。",
        "traitor_goal": "炸弹倒计时，在爆炸前逃出。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            "tracks": {"progress": {"label": "time_bomb", "target": 10, "side": "heroes"}},
            "flags": {"bomb_defused": [], "big_bomb_timer": 0},
        },
        "monsters": [],
        "actions": [
            {"id": "defuse_bomb", "side": "heroes", "label": "拆除炸弹", "detail": "知识 7+（疯子卡 5+）拆除自己的炸弹；掷出 ≤2 引爆同房所有炸弹（p56）。", "stat": "knowledge", "target": 7},
        ],
        "win_conditions": [
            {"winner": "traitor", "type": "all_heroes_dead", "reason": "所有英雄都死了。"}
        ],
        "source_pages": [56, 127],
    },
    46: {
        # 校准记录（2026-09-06，对照英雄手册 p57 / 叛徒手册 p128）：
        #   骨架原本是"驱魔仪式"的假机制（task 行动 + progress 轨道），与原版无关。
        #   机制落在 CannibalFeastMode：
        #   · 开局：阁楼（上层）放受害者=英雄数、餐厅（地面层）放食人狂徒=英雄数；
        #     两房不在场时 _ensure_room_in_play 强制入场（模板自带楼层）。
        #   · 受害者漫游：叛徒左侧玩家回合开始，直行 2 格/左转/不穿未探明门/
        #     遇英雄停（按门方位实现，比 8/20 号连通图近似更保真）。
        #   · 护送：原版回合开始免费带 2 格任意方向 → 电子版 1 行动、自动朝正门
        #     （已知简化）；正门：门厅知识检定或力量 5+，成功开门并结束回合。
        #   · 伤亡封锁：任何受害者/英雄被杀 → 全员逃生路线关闭；受害者逃出 →
        #     叛徒"吃光"路线关闭。双方胜利路线互斥门控。
        #   · 尸体与进食：被杀翻成尸体令牌；叛徒/狂徒与尸体同房且无活英雄时
        #     花整回合进食 +1 全属性（狂徒直接改怪物属性，45 号蜘蛛同款）。
        #   · 怪物互吃：狂徒回合手写力量对决吃同房受害者（引擎无怪物互攻，
        #     21/27 号口径）；受害者怪物回合完全跳过（on_monster_turn_start）。
        #   · 胜负：英雄胜 = 叛徒+狂徒全灭 或 零伤亡全员逃出；叛徒胜 = 吃光
        #     受害者 或 杀光英雄。叛徒死≠英雄胜（狂徒还在继续打），老坑 #1 吸收。
        #   · suggested_monsters 必须留空——该字段会被引擎自动 spawn（各 1 只
        #     在作祟房），46 号的受害者/狂徒全由 handler 按英雄数放置（32 号口径）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "cannibal_feast",
        "traitor_rule": "revealer",
        "hero_goal": "把所有受害者从正门送出去（保持零伤亡），或杀光叛徒与食人狂徒。",
        "traitor_goal": "吃光所有受害者，或杀光所有英雄；一旦有受害者逃出就只能杀人。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["attic", "dining_room", "entrance_hall"],
        "tokens": [{"kind": "corpse", "label": "尸体", "note": "受害者/英雄被杀后生成，叛徒与狂徒可进食"}],
        "setup": {
            # 逃出的受害者：target 在 handler.setup 里改写为实际英雄数
            "tracks": {"victims_escaped": {"label": "逃出的受害者", "target": 6, "side": "heroes"}},
            "flags": {
                "front_door_open": False,
                "blood_spilled": False,
                "victims_escaped": 0,
                "victim_escaped_any": False,
                "victim_corpses": 0,
                "escaped_hero_ids": [],
                "victim_facing": {},
            },
        },
        "monsters": [],
        "actions": [
            {"id": "unlock_front_door", "side": "heroes", "label": "撬开正门",
             "detail": "在门厅做知识检定（撬锁）或力量 5+（撞开），成功后开门并结束回合（p57）。",
             "rooms": ["entrance_hall"], "requires_flags": {"front_door_open": False}},
            {"id": "escort_victim", "side": "heroes", "label": "护送受害者",
             "detail": "带同房间的受害者沿最短路朝正门移动最多 2 格（原版为回合开始免费带行、"
                       "任意方向；电子版简化为 1 行动、自动朝门，p57）。",
             "requires": ["same_room:victim"]},
            {"id": "send_victim_out", "side": "heroes", "label": "送受害者出门",
             "detail": "正门已开时，把同房间的受害者送出正门（1 格），受害者移出游戏（p57）。",
             "rooms": ["entrance_hall"], "requires": ["same_room:victim"],
             "requires_flags": {"front_door_open": True}},
            {"id": "escape_house", "side": "heroes", "label": "逃出宅子",
             "detail": "正门已开时从门厅逃出（之后可用「重新进门」回来接人）（p57）。",
             "rooms": ["entrance_hall"], "requires_flags": {"front_door_open": True}},
            {"id": "feast_corpse", "side": "traitor", "label": "进食",
             "detail": "与尸体同房间且房内没有活着的英雄时，花整回合进食：所有属性 +1，"
                       "尸体移出游戏（p128）。狂徒也会这样做。",
             "requires": ["same_room:corpse"]},
        ],
        "win_conditions": [],
        "source_pages": [57, 128],
    },
    47: {
        # 校准记录（2026-09-06，对照英雄手册 p58 / 叛徒手册 p129）：
        #   骨架原本是"止血"假机制（task 行动 + progress 轨道），与原版无关。
        #   机制落在 OuroborosMode：
        #   · 开局（p129）：叛徒移出游戏（物品掉揭示房、Girl/Dog/Madman 被
        #     吞掉弃置），两个蛇头放揭示房；骷髅不在掉落堆时补一张（28 号口径，
        #     强制触发局叛徒未必持有骷髅预兆）。
        #   · 蛇头行动（p129）：每头掷 1 骰定步数；离开的房间放 1 节蛇身
        #     （每房限 1 枚、可穿过已放的）；不走密道/秘门/神秘电梯；
        #     可探索新房间并忽略符号；探索者不影响蛇头。
        #   · 施咒（p58）：持骷髅者与蛇头同房理智 5+ → 该头力量降 5、解锁攻击
        #     （未施咒的蛇头 attack_allowed 拦截）。
        #   · 击杀（p58/p129）：施咒后每次击败=1 hit，需 ceil(玩家数/2) 次
        #     （3-4 人 2 次、5-6 人 3 次）；不可击晕（on_monster_defeated 拦下计数）。
        #   · 免疫（p58/p129）：速度攻击无效（monsters spec 声明 immune_to，
        #     spawn=deferred 只进 monster_specs 不自动 spawn，蛇头由 handler 放置）。
        #   · 胜负（p58/p129）：英雄胜 = 双头皆斩；叛徒胜 = 16 节蛇身进场。
        #     叛徒开局出局（变蛇）→ 必须吸收"叛徒死亡→英雄胜"兜底（10 号同款）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "worm_ouroboros",
        "traitor_rule": "revealer",
        "hero_goal": "捡起骷髅对蛇头施削弱咒（理智 5+，力量降 5），再围殴累计重击斩下双头。",
        "traitor_goal": "双头游走留下蛇身，16 节蛇身全部进场即可碾碎房子。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [{"kind": "ouroboros_body", "label": "蛇身", "note": "蛇头离开的房间各留 1 节，16 节铺满即叛徒胜"}],
        "setup": {
            "tracks": {"ouroboros_body": {"label": "蛇身节数", "target": 16, "side": "traitor"}},
            "flags": {
                "weakened_heads": [],
                "head_hits": {},
                "hits_needed": 2,
                "body_left": 16,
            },
        },
        "monsters": [
            {"template_id": "ouroboros_head", "spawn": "deferred", "immune_to": ["speed"],
             "name": "衔尾蛇头"},
        ],
        "actions": [
            {"id": "cast_weakening_spell", "side": "heroes", "label": "施放削弱咒",
             "detail": "持有骷髅并与蛇头同房间时，做理智 5+ 检定（每回合一次）：成功后该蛇头"
                       "力量降为 5，此后可被攻击（p58）。",
             "stat": "sanity", "target": 5,
             "requires": ["omen_skull", "same_room:ouroboros_head"]},
        ],
        "win_conditions": [],
        "source_pages": [58, 129],
    },
    48: {
        # 校准记录（2026-09-06，对照英雄手册 p59 / 叛徒手册 p130）：
        #   骨架原本是"雕像花园"假机制（h48_hero_task + hero_progress 轨道），
        #   且 47/48 的原文标题在骨架表上错位。机制落在 CrimsonJackMode：
        #   · 开局（p130）：杰克放门厅（前门旁），叛徒仍在场未出局。
        #   · 打不死（p130）：被击败不晕不伤，只是暂时移出；叛徒下回合
        #     开始时回到门厅，且每次回归全属性 +1（flags["jack_bonus"]）。
        #   · 恐惧光环（p59/p130）：与杰克同房的英雄回合开始须理智 3+，
        #     失败各掉 1 点精神属性与 1 点物理属性。
        #   · 找武器（p59）：图书馆/教堂/金库（须 data["opened"]）/阁楼
        #     知识 3+，成功取斧/矛/血匕首之一并洗匀该牌堆。
        #   · 研究（p59）：持武器者力量 5+ 或知识 5+，累计玩家数枚令牌
        #     即理解用法（flags["cursed_weapon_understood"]）。
        #   · 永杀（p59）：理解用法后用该武器击败 → 杰克永久死亡，英雄胜。
        #   · 胜负：英雄胜 = 诅咒武器永杀；叛徒胜 = 英雄全灭。叛徒被杀而
        #     杰克还在时杰克继续行动（7/8 号口径），故吸收兜底。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "cursed_weapon",
        "traitor_rule": "revealer",
        "hero_goal": "在图书馆/教堂/金库/阁楼找到诅咒武器，研究明白用法后用它永久杀死血腥杰克。",
        "traitor_goal": "让血腥杰克杀光所有英雄——他每次回归都会更强。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["entrance_hall", "library", "chapel", "vault", "attic"],
        "tokens": [],
        "setup": {
            # 研究进度：target 在 handler.setup 里改写为玩家数
            "tracks": {"study_tokens": {"label": "研究进度", "target": 6, "side": "heroes"}},
            "flags": {
                "jack_bonus": 0,
                "jack_banished": False,
                "jack_killed": False,
                "cursed_weapon": None,
                "cursed_weapon_understood": False,
            },
        },
        "monsters": [
            # spawn=deferred：只进 monster_specs，由 handler 放进门厅
            {"template_id": "crimson_jack", "spawn": "deferred", "name": "血腥杰克"},
        ],
        "actions": [
            {"id": "search_cursed_weapon", "side": "heroes", "label": "搜寻诅咒武器",
             "detail": "在图书馆/教堂/金库（须已开）/阁楼做知识 3+ 检定（每回合一次）："
                       "成功后从对应牌堆取一件自选诅咒武器（斧/矛/血匕首）并洗匀该堆（p59）。",
             "stat": "knowledge", "target": 3,
             "rooms": ["library", "chapel", "vault", "attic"]},
            {"id": "study_cursed_weapon", "side": "heroes", "label": "研究诅咒武器",
             "detail": "持有诅咒武器时做力量 5+ 或知识 5+（每回合一次）：每成功一次 +1 枚"
                       "研究令牌，累计到玩家数即理解用法，此后可用它永久杀死血腥杰克（p59）。",
             "stat": "might", "target": 5, "progress": "study_tokens"},
        ],
        "win_conditions": [],
        "source_pages": [59, 130],
    },
    49: {
        # 校准记录（2026-09-07，对照英雄手册 p60 / 叛徒手册 p131）：
        #   骨架原本是"荆棘女巫"假机制（错位的 15 号文案 + progress 轨道）。
        #   机制落在 AstralSpiritMode：
        #   · 开局（p130/p131）：星界灵放叛徒房间；英雄灵魂出窍——电子版把
        #     灵魂与昏迷肉体建在同一位英雄身上（位置即肉体位置，玩家继续
        #     扮演自己的灵魂，无需独立灵魂令牌）。
        #   · 灵魂规则（p60，保真）：英雄不能探索新房间；攻击/防御只能用
        #     知识/理智（attack_attr_override 覆盖力量/速度为较高精神属性）；
        #     攻击星界灵失败不受伤（attack_loss_damage_disabled）。
        #   · 摧毁星界灵（p60）：攻击成功不造成伤害，改为 +1 枚驱逐令牌
        #     （星界灵不晕不死）；累计玩家数枚 → 摧毁 → 英雄胜。
        #   · 星界灵攻击（p131）：on_monster_turn_attack 接管为知识对决，
        #     差值即精神伤害；被击败则无事发生。
        #   · 毁灭灵魂（p131）：叛徒攻击英雄——电子版简化为标准对决（原版
        #     无防御固定 2 骰精神伤）；精神属性到骷髅 = 灵魂被毁，英雄出局，
        #     肉体进无魂名单（从此不能被附身）。
        #   · 附身仪式（p131）：星界灵回合移向最近的无魂肉体，同房理智掷骰
        #     须高于起始理智（用属性轨道上限近似），累计玩家数枚 → 附身，
        #     叛徒胜。
        #   · 胜负：英雄胜 = 摧毁星界灵；叛徒胜 = 附身或灵魂全灭。叛徒被杀
        #     而星界灵还在时星界灵继续行动（7/8 号口径），故吸收兜底。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "astral_spirit",
        "traitor_rule": "revealer",
        "hero_goal": "以知识/理智攻击星界灵累积驱逐令牌（玩家数枚），摧毁它回到肉体。",
        "traitor_goal": "让星界灵磨灭所有灵魂，或附身一具无魂肉体。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            # 驱逐进度：target 在 handler.setup 里改写为玩家数
            "tracks": {"banish_tokens": {"label": "驱逐星界灵", "target": 6, "side": "heroes"}},
            "flags": {
                "spirit_destroyed": False,
                "spirit_inhabited": False,
                "soulless": {},
            },
        },
        "monsters": [
            # spawn=deferred：只进 monster_specs，由 handler 放到叛徒房间
            {"template_id": "astral_spirit", "spawn": "deferred", "name": "星界灵"},
        ],
        "actions": [],
        "win_conditions": [],
        "source_pages": [60, 131],
    },
    50: {
        # 校准记录（2026-09-07，对照英雄手册 p61 / 叛徒手册 p132）：
        #   骨架原本是"礼物盒子"假机制（错位的 10 号文案 + task 行动）。
        #   机制落在 NightMurderMode：
        #   · 开局（p132）：仆人数 = 英雄数；前三个尽量各占一层空房，多余
        #     放任意空房，空房不足时平均分配到已占用房间（21/28 号口径）。
        #   · 夜晚推进（p132）：叛徒回合结束推进 night_timer；叛徒若已死由
        #     "本轮最后存活玩家"代跑——p132 明说叛徒死了照样能赢，计时器
        #     绝不能因叛徒出局停摆（4 号 spider_timer 同款坑的预防）。
        #   · 强化表（p132）：0-3→3/3/3、4-7→4/4/4、8→5/5/5、9→6/6/6，
        #     每次推进后重算全体仆人属性（45 号蜘蛛成长同款写法）。
        #   · 胜负（p61/p132）：night_timer 到 10（日出）→ 存活英雄胜；
        #     黎明前英雄全灭 → 叛徒胜；叛徒出局吸收"叛徒死→英雄胜"兜底。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "night_survival",
        "traitor_rule": "revealer",
        "hero_goal": "在房子里撑到天亮（夜晚进度 10），活着的继承人平分遗产。",
        "traitor_goal": "让仆人在黎明前杀光所有英雄——叛徒就算死了也一样赢。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            # 夜晚进度：推进到 10 即日出
            "tracks": {"night_timer": {"label": "夜晚进度（日出）", "target": 10, "side": "heroes"}},
            "flags": {},
        },
        "monsters": [
            # spawn=deferred：只进 monster_specs，由 handler 按楼层布点
            {"template_id": "servant", "spawn": "deferred", "name": "贪婪仆人"},
        ],
        "actions": [],
        "win_conditions": [],
        "source_pages": [61, 132],
    },
    51: {
        # 校准记录（2026-09-05，对照英雄手册 p62 / 叛徒手册 p133）：
        #   机制落在 DarkerThanNightMode：
        #   · 镜面房间（6 间）创造圣印（理智 4+，每房限一枚）
        #   · 叛徒分身在镜面房间繁殖（每房限一只）；圣印阻止繁殖
        #   · 叛徒受伤可用分身抵消（消耗一只分身）
        #   · 黑暗仪式：外缘房间知识 5+ 放 Hex 令牌，3 枚 → 叛徒胜
        #   · 英雄胜利：圣印数 = 玩家数 或 叛徒死亡
        #   简化：分身不可被普通攻击/ consecrated weapon 未建模；
        #     破解圣印（Sanity 5+）未建模；叛徒不可直接攻击英雄未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "darker_than_night",
        "traitor_rule": "revealer",
        "hero_goal": "在镜面房间创造圣印，把黑暗从房子里驱逐出去。",
        "traitor_goal": "在房子里种下 3 枚黑暗 Hex，或让分身吃掉所有英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["bedroom", "chapel", "conservatory", "dining_room", "grand_staircase", "master_bedroom", "balcony", "garden", "graveyard", "patio", "tower"],
        "tokens": ["holy_seal", "dark_hex"],
        "setup": {
            "tracks": {
                "hero_progress": {"label": "圣印数", "target": "player_count", "side": "heroes"},
            },
            "flags": {"dark_hexes": 0, "seal_rooms_used": []},
        },
        "monsters": [],
        "actions": [
            {"id": "create_seal", "side": "heroes", "label": "创造圣印", "detail": "在镜面房间做理智 4+，每房限一枚（p62）。", "stat": "sanity", "target": 4, "rooms": ["bedroom", "chapel", "conservatory", "dining_room", "grand_staircase", "master_bedroom"], "progress": "hero_progress"},
        ],
        "win_conditions": [
            {"winner": "traitor", "type": "all_heroes_dead", "reason": "黑暗吞噬了最后的英雄。"}
        ],
        "source_pages": [62, 133],
    },
    52: {
        # 校准记录（2026-09-05，对照英雄手册 p63 / 叛徒手册 p134）：
        #   机制落在 CracklingAuraMode：
        #   · 叛徒召唤恶魔领主（五芒星室，知识 5+，Might 7 Speed 5 Sanity 4）
        #   · 魔法尘：英雄在事件房掷 3 骰（水晶球 4 骰）4+ → 获得魔法尘；
        #     丢弃→ 反魔法场（叛徒不可在其中施法/召唤）
        #   · 英雄胜：叛徒死 + 无恶魔在场
        #   简化：叛徒法术系统（火球/传送/回程）未建模；
        #     反魔法场回合清除未建模（持续到被覆盖）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "ring_exorcism",
        "traitor_rule": "revealer",
        "hero_goal": "搜索魔法尘创建反魔法场，杀死叛徒并驱逐所有恶魔。",
        "traitor_goal": "召唤恶魔领主杀死所有英雄。",
        "suggested_monsters": ["giant"],
        "required_cards": [],
        "key_rooms": ["pentagram_chamber"],
        "tokens": ["magic_dust", "demon_lord"],
        "setup": {
            "tracks": {
                "demon_slain": {"label": "已驱逐恶魔", "target": 10, "side": "heroes"},
            },
            "flags": {"anti_magic_rooms": [], "demon_alive": False},
        },
        "monsters": [
            {"template_id": "giant", "name": "恶魔领主", "spawn": "deferred", "count": 1, "speed": 5, "might": 7, "sanity": 4},
        ],
        "actions": [
            {"id": "search_dust", "side": "heroes", "label": "搜索魔法尘", "detail": "在有事件图标的房间掷 3 骰（水晶球 4 骰）4+（p63）。"},
            {"id": "drop_dust", "side": "heroes", "label": "散布魔法尘", "detail": "把魔法尘丢在地上创建反魔法场（p63）。"},
        ],
        "win_conditions": [
            {"winner": "heroes", "type": "traitor_dead", "reason": "叛徒被杀，恶魔被驱逐。"}
        ],
        "source_pages": [63, 134],
    },
    53: {
        # 校准记录（2026-09-05，对照英雄手册 p64 / 叛徒手册 p135）：
        #   机制落在 ToxicObjectEscapeMode：
        #   · 死亡之物（令牌）由狗携带（Speed 6 Might 4）；可被偷/掉落
        #   · 毒云：有物之房间放 token；进入掷骰（2 无/1 -1 物理/0 -1 物理-1 精神）；
        #     回合结束在有物或毒云房间 -1 全属性
        #   · 逃跑：清障碍（力量 4+）→ 解锁（知识 5+）→ 逃离（2 格移动）
        #   · 净化：在熔炉房/地下湖开始回合持物 → 净化
        #   · 英雄胜：半数英雄逃出 或 净化+半数存活
        #   简化：狗掉落物品（2+ 物理伤害）未建模；
        #     毒云逐回合扩展未建模（仅在有物房间放 token）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "toxic_object_escape",
        "traitor_rule": "revealer",
        "hero_goal": "净化死亡之物或从正门逃出——避开毒云。",
        "traitor_goal": "让毒气杀死所有英雄。",
        "suggested_monsters": ["dog"],
        "required_cards": [],
        "key_rooms": ["entrance_hall", "furnace_room", "underground_lake"],
        "tokens": ["deathly_object", "poison_cloud"],
        "setup": {
            "tracks": {
                "barricade_tokens": {"label": "已清除障碍", "target": "player_count", "side": "heroes"},
                "escaped_count": {"label": "已逃出英雄", "target": "half_players_ceil", "side": "heroes"},
            },
            "flags": {"object_cleansed": False, "door_unlocked": False, "escaped": []},
        },
        "monsters": [
            {"template_id": "dog", "name": "地狱犬", "spawn": "haunt_room", "count": 1, "speed": 6, "might": 4, "sanity": 0},
        ],
        "actions": [
            {"id": "clear_barricade", "side": "heroes", "label": "清除障碍", "detail": "在门厅做力量 4+，推进障碍清除计数（p64）。", "stat": "might", "target": 4, "rooms": ["entrance_hall"], "progress": "barricade_tokens"},
            {"id": "unlock_door", "side": "heroes", "label": "解锁前门", "detail": "障碍清完后在门厅做知识 5+（p64）。", "stat": "knowledge", "target": 5, "rooms": ["entrance_hall"], "requires_flags": {"door_unlocked": False}},
            {"id": "flee_house", "side": "heroes", "label": "逃离房子", "detail": "门开后花 2 格移动逃离（p64）。", "requires_flags": {"door_unlocked": True}},
            {"id": "cleanse_object", "side": "heroes", "label": "净化死亡之物", "detail": "在熔炉房/地下湖开始回合持物（p64）。"},
        ],
        "win_conditions": [],
        "source_pages": [64, 135],
    },
    54: {
        # 校准记录（2026-09-05，对照英雄手册 p65 / 叛徒手册 p136）：
        #   机制落在 ArkanokSkullMode：
        #   · 骷髅 token 放作祟房间；遗骸在六类房间之一（叛徒知道）
        #   · 侦测：持骷髅/圣徽 → 理智 4+；持水晶球/灵应板 → 知识 5+
        #   · 净化：持骷髅在遗骸房间理智 5+
        #   · 僵尸：2× 英雄数，Speed 1 Might 4 Sanity 2
        #   · 英雄胜：净化遗骸；叛徒胜：英雄全灭
        #   简化：僵尸擒抱未建模（正常怪物攻击）；叛徒死亡变鬼未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "arkanok_skull",
        "traitor_rule": "revealer",
        "hero_goal": "找到 Ar'Kanok 的遗骸所在房间，持骷髅前往净化。",
        "traitor_goal": "让僵尸杀死所有英雄。",
        "suggested_monsters": ["zombie"],
        "required_cards": [],
        "key_rooms": ["chapel", "crypt", "graveyard", "furnace_room", "bloody_room", "charred_room"],
        "tokens": ["skull"],
        "setup": {
            "tracks": {
                "ritual_progress": {"label": "净化进度", "target": 1, "side": "heroes"},
            },
            "flags": {"remains_room": None, "remains_found": False, "skull_picked": False},
        },
        "monsters": [
            {"template_id": "zombie", "name": "僵尸", "spawn": "deferred", "count": 1, "speed": 1, "might": 4, "sanity": 2},
        ],
        "actions": [
            {"id": "detect_remains", "side": "heroes", "label": "侦测遗骸", "detail": "持骷髅/圣徽理智 4+ 或持水晶球/灵应板知识 5+（p65）。"},
            {"id": "exorcise", "side": "heroes", "label": "净化 Ar'Kanok", "detail": "持骷髅在遗骸房间理智 5+（p65）。", "stat": "sanity", "target": 5, "requires_flags": {"remains_found": True}, "progress": "ritual_progress"},
        ],
        "win_conditions": [],
        "source_pages": [65, 136],
    },
    55: {
        # 校准记录（2026-09-05，对照英雄手册 p66 / 叛徒手册 p137）：
        #   机制落在 KingsRoadsMode：
        #   · 驱魔检定：知识 5+（实验室/电梯/水晶球）或理智 5+
        #     （教堂/温室/地窖/面具）；每房/每预兆一次
        #   · 影子：每玩家一只，从最近入口追击英雄
        #   · 国王之路：简化为影子正常追击（路网传送未建模）
        #   · 英雄胜：驱魔数 = 玩家数；叛徒胜：英雄全灭
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "kings_roads",
        "traitor_rule": "revealer",
        "hero_goal": "在影子附身之前完成驱魔，封住国王之路。",
        "traitor_goal": "让影子附身所有英雄。",
        "suggested_monsters": ["shadow"],
        "required_cards": [],
        "key_rooms": ["research_laboratory", "chapel", "conservatory", "crypt", "mystic_elevator", "garden", "graveyard", "patio", "tower", "balcony"],
        "tokens": [],
        "setup": {
            "tracks": {
                "disenchant_progress": {"label": "驱魔进度", "target": "player_count", "side": "heroes"},
            },
            "flags": {"used_sources": []},
        },
        "monsters": [
            {"template_id": "ghost", "name": "影子", "spawn": "deferred", "count": "player_count", "speed": 3, "might": 0, "sanity": 0},
        ],
        "actions": [
            {"id": "disenchant_room", "side": "heroes", "label": "驱魔检定", "detail": "在实验室/教堂/温室/地窖做知识或理智 5+（p66）。", "stat": ["knowledge", "sanity"], "target": 5, "progress": "disenchant_progress"},
        ],
        "win_conditions": [],
        "source_pages": [66, 137],
    },
    56: {
        # 校准记录（2026-09-08，对照英雄手册 p67 / 叛徒手册 p138）：
        #   骨架原本是"夺回时间之沙"假机制（h56_hero_task + 进度轨道）。
        #   机制落在 SandsOfTimeMode：
        #   · 开局（p138）：幽影（spectre）= 英雄数，放作祟房；叛徒立即
        #     戴面具：+2 知识、-2 理智（理智死亡保护到骷髅上一格，p138 明文）。
        #   · 幽影（p138/p67）：免疫力量攻击（monster_specs immune_to）；
        #     理智攻击接管（on_monster_turn_attack，精神伤害）；穿墙移动
        #     （同层正交邻格，p138 明文"无需门"；上下楼通道简化）。
        #   · 时间之力（p138，每次 flags["time_track"] +1、无上限）：
        #     命运之风（+2 移动）、时停打击（造成 ≥1 伤害跳过下回合，
        #     重构为显式行动）、补充时沙（知识 3+，每只同房幽影轨道 -1、
        #     同房幽影全晕）。
        #   · 失控检定（p67）：叛徒回合结束（叛徒死由最后存活玩家代跑）
        #     掷玩家数骰，≤ 轨道 → 叛徒全属性 -1、轨道 -1、循环再掷。
        #   · 欺骗命运（p67）：持水晶球或独处 + 同房幽影 → 知识 4+ 放逐。
        #   · 戒指/奖章：持戒指理智攻幽影（attack_attr_override）；持奖章
        #     落败免伤（attack_loss_damage_disabled）。
        #   · 胜负（p67/p138）：英雄胜 = 叛徒死（失控磨损同算）；叛徒胜 =
        #     英雄全灭。叛徒死即英雄胜，无需吸收兜底。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "time_sands",
        "traitor_rule": "revealer",
        "hero_goal": "杀死叛徒（逼他滥用时间之力直到失控自毁），或直接击杀。",
        "traitor_goal": "用时间之力与幽影杀光所有英雄——但每次使用都在自毁。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            # 时之沙掌控：flags["time_track"] 记真实值（无上限），此轨道封顶显示
            "tracks": {"time_track": {"label": "时之沙掌控（失控线）", "target": 10, "side": "traitor"}},
            "flags": {
                "time_track": 0,
                "skip_turn_ids": [],
            },
        },
        "monsters": [
            # spawn=deferred：只进 monster_specs，由 handler 放作祟房
            {"template_id": "spectre", "spawn": "deferred", "immune_to": ["might"],
             "name": "记忆幽影"},
        ],
        "actions": [
            {"id": "cheat_fate", "side": "heroes", "label": "欺骗命运",
             "detail": "与幽影同房间，且持有水晶球或房内没有其他英雄时：做知识 4+ 检定，"
                       "成功则该幽影立即移出游戏（p67）。每回合一次。",
             "stat": "knowledge", "target": 4, "requires": ["same_room:spectre"]},
            {"id": "winds_of_fate", "side": "traitor", "label": "命运之风",
             "detail": "本回合获得 2 点额外移动力；时之沙轨道 +1（p138）。每回合一次。",
             "stat": "knowledge", "target": 0},
            {"id": "time_stop_strike", "side": "traitor", "label": "时停打击",
             "detail": "对同房间的英雄做力量攻击；若造成至少 1 点伤害，该英雄跳过下个回合。"
                       "时之沙轨道 +1（p138，重构为显式行动）。每回合一次。",
             "stat": "might", "target": 0},
            {"id": "replenish_sands", "side": "traitor", "label": "补充时沙",
             "detail": "与幽影同房间时做知识 3+ 检定：成功则每只同房幽影使时之沙轨道 -1"
                       "（最低 0）；无论成败，同房幽影全部被击晕（p138）。每回合一次。",
             "stat": "knowledge", "target": 3, "requires": ["same_room:spectre"]},
        ],
        "win_conditions": [],
        "source_pages": [67, 138],
    },
    57: {
        # 精修 v3（M10-1）：对照英雄手册 p68 / 叛徒手册 p139 逐字重写，
        # 逻辑落在 haunt_modes.PortraitCurseMode。
        #   · 颜料（p68）：令牌数 = 英雄数 + 2，只放阁楼/废弃房/坍塌房/露台/
        #     雕像走廊/储藏室/酒窖，每间一枚；房间比令牌多时优先放"离任何
        #     探险者最远"的房间，多出的令牌搁置、待这些房间被发现时补放。
        #   · 重绘（p68）：英雄在画廊持一枚颜料做知识 4+，成功则颜料耗尽并
        #     在房内放一枚知识检定令牌；集满"作祟开始时的英雄数"破除诅咒。
        #   · 无敌（p139）：事件、房间特征与伤害都不能削减叛徒属性（仅持
        #     远古护身符的英雄在肉搏中打赢他是例外）；本剧本没有怪物。
        #   · 肖像（p139）：叛徒进入画廊或回合开始即在画廊 → 理智 4+，失败
        #     吃 1 骰精神伤害——唯一无视其免疫的伤害，也是他能被杀死的途径。
        #   · 胜负（p68/p139）：英雄胜 = 集满知识检定令牌 或 叛徒死亡；
        #     叛徒胜 = 销毁 3 枚颜料 或 英雄全灭（后两条引擎通用规则兜底）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "portrait_curse",
        "traitor_rule": "revealer",
        "hero_goal": "把颜料送进画廊反复重绘肖像，或逼叛徒自己毁在画像前。",
        "traitor_goal": "销毁三枚颜料，或杀光所有英雄——他本人刀枪不入。",
        "suggested_monsters": [],
        "required_cards": [],
        # key_rooms 故意留空：bot_ai._haunt_goal_rooms 会把这里的每一间都当成
        # 常驻寻路目标，于是"颜料已被拿走的颜料房"和"画廊"平级地把英雄来回拉扯
        # （实测 seed=109/4p 英雄在两个房间之间踱步，重绘 0/3）。本剧本的目标
        # 完全由 PortraitCurseMode.bot_goal_rooms 按"手里有没有颜料"动态给出。
        "key_rooms": [],
        "tokens": ["paint", "knowledge_check"],
        "setup": {
            # repaint 的上限在 setup 里按"作祟开始时活着的英雄数"重写：
            # 通用 hero_count 换算只数当前活人，英雄中途阵亡会让目标缩水。
            "tracks": {
                "repaint": {"label": "英雄：重绘肖像（知识检定令牌）", "target": "hero_count", "side": "heroes"},
                "paint_destroyed": {"label": "叛徒：销毁颜料", "target": 3, "side": "traitor"},
            },
            "flags": {
                "spell_broken": False,
                "paint_total": 0,
                "pending_paint": 0,
                "repaint_needed": 0,
                "destroyed_this_turn": False,
            },
        },
        "monsters": [],
        "actions": [
            # 重绘排在取用之前：bot 按标签打分相同，靠列表顺序优先做关键动作。
            # 两个行动都不写 rooms——写了就会变成机器人的常驻目标（见上）。
            # "在画廊""房间里有颜料"这两条限制由 handler 把关。
            {"id": "repaint_portrait", "side": "heroes", "label": "重绘肖像",
             "detail": "在画廊随身携带一枚颜料时做知识 4+ 检定：成功则颜料耗尽，"
                       "并在画廊放上一枚知识检定令牌；集满英雄数即破除诅咒（p68）。",
             "stat": "knowledge", "target": 4, "progress": "repaint"},
            {"id": "take_paint", "side": "both", "label": "拿起颜料",
             "detail": "收走本房间的一枚颜料令牌。每人同时只能携带一枚（p68）。"},
            {"id": "pass_paint", "side": "heroes", "label": "把颜料交给队友",
             "detail": "把随身颜料交给同房间没带颜料的英雄——颜料可以像普通物品"
                       "一样交易（p68）。",
             "requires": ["same_room:hero"]},
            {"id": "drop_paint", "side": "both", "label": "放下颜料",
             "detail": "把随身颜料留在当前房间（p68：可被捡起、交易与抢夺）。"},
            {"id": "destroy_paint", "side": "traitor", "label": "销毁颜料",
             "detail": "毁掉随身携带的一枚颜料，代替本回合的一次攻击；"
                       "毁满 3 枚即胜（p139）。"},
        ],
        "win_conditions": [
            {"winner": "heroes", "type": "flag", "flag": "spell_broken",
             "reason": "最后一笔落下，肖像交出了它封存三百年的力量。"},
            {"winner": "traitor", "type": "track", "track": "paint_destroyed",
             "operator": ">=", "target": 3,
             "reason": "颜料毁尽，再没有人能触碰那幅画。"},
        ],
        "source_pages": [68, 139],
    },
    58: {
        # 校准记录（2026-09-09，对照英雄手册 p69 / 叛徒手册 p140）：
        #   骨架原本是"驱散暮光与噩梦"假机制（h58_hero_task + 进度轨道）。
        #   机制落在 NightfallMode：
        #   · 开局（p69/p140）：熔炉房不在场则取牌放入（_ensure_room_in_play，
        #     3/28 号先例）；噩梦 = 英雄数，铺在带事件图标且离最近英雄 ≥4 格
        #     的房间，不够远则取尽可能远的房，尽量均匀分布。
        #   · 暮色（p69/p140）：除熔炉房/花园/墓地/天井/阳台/塔楼外全屋皆暮色；
        #     叛徒所在房间永远是暮色（即使已死）；已驱散的楼层与有火把的房间
        #     不算暮色。朝外窗房间未建模（内容库无该标记）。
        #   · 火把（p69）：熔炉房造火把代替攻击；抵消同房间暮色；叛徒同房时
        #     只有持火把者受保护（已按原文实现）；每人限一支。
        #   · 消灭噩梦（p69）：受 2 点以上伤害即摧毁，更少只击晕（阈值统一
        #     按 2——on_monster_defeated 钩子不提供伤害类型，原文精神阈值为 3）。
        #   · 驱散暮色（p69）：同房间 ≥2 名活英雄且至少一人持火把 → 发起者结算
        #     同房全员各一次知识 4+ 或理智 4+，需两类各至少一次成功 → 该层
        #     驱散；三层全驱散 → 英雄胜。做检定者本回合禁移动/攻击。
        #   · 缠梦（p140）：噩梦造成 ≥2 精神伤害时改为缠住该英雄；被缠者回合
        #     开始理智 5+ 挣脱，失败受 1 骰精神伤害；缠梦中的噩梦不行动、
        #     不可被攻击。
        #   · 暮色战斗（p69/p140）：暮色中不能力量/速度攻击，改用知识攻击
        #     （attack_attr_override 覆盖），持火把者不受限。
        #   · 胜负（p69/p140）：英雄胜 = 噩梦全灭或三层暮色全驱散；叛徒胜 =
        #     英雄全灭。叛徒出局时噩梦照常行动，吸收兜底（7/8 号口径）。
        #   已知简化：暮色"用 Sanity 代替 Speed 决定移动力"未建模（引擎无该
        #     钩子）；墓色中禁用武器/左轮限制、蜡烛与水晶球加骰未建模；缠梦
        #     英雄"被叛徒操控"未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "nightfall_twilight",
        "traitor_rule": "revealer",
        "hero_goal": "在熔炉房点起火把，逐层驱散暮色（三层全清即胜），或直接消灭所有噩梦。",
        "traitor_goal": "让噩梦与暮色吞没所有英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["furnace_room"],
        "tokens": ["nightmare", "torch", "twilight"],
        "setup": {
            # 暮色驱散按层计（flags["banished_floors"]），轨道用于 UI 进度
            "tracks": {"banished_floors": {"label": "已驱散楼层", "target": 3, "side": "heroes"}},
            "flags": {
                "banished_floors": [],
                "torches": {},
                "haunting": {},
                "furnace_key": None,
            },
        },
        "monsters": [
            # spawn=deferred：只进 monster_specs，由 handler 按"远离英雄的事件房"布点
            {"template_id": "nightmare", "spawn": "deferred", "name": "噩梦"},
        ],
        "actions": [
            {"id": "create_torch", "side": "heroes", "label": "点燃火把",
             "detail": "在熔炉房代替攻击点燃一支火把（每人限一支）：火把抵消同房间的"
                       "暮色，持火把者永不受暮色影响（p69）。",
             "stat": "sanity", "target": 0, "rooms": ["furnace_room"]},
            {"id": "banish_twilight", "side": "heroes", "label": "驱散暮色",
             "detail": "同房间至少 2 名英雄且至少一人持火把时：同房全员各做一次知识 4+ 或"
                       "理智 4+，两类各至少一次成功即驱散该层暮色；参与检定者本回合"
                       "不能移动或攻击（p69）。每回合一次。",
             "stat": "knowledge", "target": 4},
        ],
        "win_conditions": [],
        "source_pages": [69, 140],
    },
    59: {
        # 校准记录（2026-09-09，对照英雄手册 p70 / 叛徒手册 p141）：
        #   骨架原本是"徽章诅咒"假机制（h59 任务 + 进度轨道）。
        #   机制落在 ForAThousandYearsMode：
        #   · 开局（p141）：女巫 + 雕像放带预兆图标的房间（除作祟房，无则
        #     任意房）；英雄数 ≥3 → 熊（预兆图标空房，无则女巫房）、≥4 →
        #     猫（女巫房）、≥5 → 信徒（叛徒房）。徽章（omen_medallion）确保
        #     在叛徒手里（47 号骷髅兜底同口径）。
        #   · 徽章归属：flags["medallion_holder"] 统一追踪（traitor/monster/
        #     hero:<id> / None=地上）；英雄持有时同步把卡放进 items。
        #   · 持徽章英雄每回合最多移动 2 格（on_player_moved 计数 +
        #     movement_stopped；叛徒不限速——原文只限英雄）。
        #   · 放置徽章（p70）：持徽章者在雕像房速度掷骰 ≥ 房间内未昏迷对手数
        #     （叛徒+怪物）的两倍 → 挂上雕像 → 英雄胜。
        #   · 摧毁徽章（p141）：持有者（叛徒/怪物）在塔楼/地下湖结束回合 →
        #     扔下徽章 → 叛徒胜（check_victory 检查）。
        #   · 怪物攻击（p141）：女巫知识攻击（目标理智防御、精神伤害）；熊
        #     力量 +2 骰；猫速度攻击（目标速度防御、物理）；猫/信徒造成 ≥2
        #     伤害且目标持徽章 → 偷走徽章。
        #   · 徽章易手：怪物可拾取地上徽章（on_monster_turn_start）；怪物被
        #     击败/击晕时徽章掉地上（on_monster_defeated），英雄拾取即持有。
        #   · 胜负（p70/p141）：英雄胜 = 徽章挂上雕像；叛徒胜 = 徽章扔进
        #     塔楼/地下湖，或英雄全灭。叛徒出局时女巫使魔继续行动，
        #     吸收兜底（7/8 号口径）。
        #   已知简化：拖拽昏迷怪物、怪物探索新房间、熊/猫禁用特殊通道、
        #     猫坠落即晕、徽章"仅回合开始可弃/交易"与"狗不能携带"均未建模。
        #   专属怪物模板 curse_witch/curse_bear/curse_cat/curse_cultist（属性
        #     与 3 号的 witch/cat 不同，避免语义混淆）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "badge_curse",
        "traitor_rule": "revealer",
        "hero_goal": "从叛徒手里夺回王室徽章（或在它落地时捡起），护送到雕像房挂上去即破咒。",
        "traitor_goal": "让女巫使魔抢走徽章并扔进塔楼或地下湖，或杀光所有英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["tower", "underground_lake"],
        "tokens": ["royal_statue", "witch", "bear", "cat", "cultist"],
        "setup": {
            "tracks": {"medallion": {"label": "王室徽章", "target": 1, "side": "heroes"}},
            "flags": {
                "medallion_holder": None,
                "medallion_steps": {},
                "statue_key": None,
            },
        },
        "monsters": [
            # spawn=deferred：只进 monster_specs，由 handler 按预兆图标房布点
            {"template_id": "curse_witch", "spawn": "deferred", "name": "诅咒女巫"},
            {"template_id": "curse_bear", "spawn": "deferred", "name": "女巫之熊"},
            {"template_id": "curse_cat", "spawn": "deferred", "name": "女巫之猫"},
            {"template_id": "curse_cultist", "spawn": "deferred", "name": "女巫信徒"},
        ],
        "actions": [
            {"id": "place_medallion", "side": "heroes", "label": "挂上王室徽章",
             "detail": "持徽章者在雕像所在房间做速度掷骰：结果 ≥ 房间内未昏迷对手数"
                       "（叛徒+怪物）的两倍即成功，诅咒破除、英雄获胜（p70）。",
             "stat": "speed", "target": 0, "requires": ["same_room:royal_statue"]},
        ],
        "win_conditions": [],
        "source_pages": [70, 141],
    },
    60: {
        # 校准记录（2026-09-09，对照英雄手册 p71 / 叛徒手册 p142）：
        #   骨架原本是"燃烧之沙"假机制（h60 任务 + 进度轨道）。
        #   机制落在 BurningSandsMode：
        #   · 开局（p140）：斯芬克斯（Speed 3 / Might 5 / Sanity 3 / Know 4）
        #     = 英雄数，全部放门厅（_ensure_room_in_play 保证门厅在场）。
        #   · 三线索（p71/p142，双方同规则、各自集齐）：垃圾房力量 4+、
        #     游戏室速度 4+、管风琴房理智 4+；成功后英雄抽一张事件牌；
        #     每回合一条检定（引擎 haunt action 限额天然满足）。
        #   · 解谜（p71/p142）：集齐三线索后在作祟房做知识检定——英雄 6+
        #     （持水晶球/灵应板 +1 骰未建模，见简化）、叛徒 5+；英雄成功
        #     → 英雄胜，叛徒成功 → 叛徒胜。
        #   · 斯芬克斯拦路（p71/p142）：英雄离开有未晕斯芬克斯的房间，该步
        #     成本每只 3 点（movement_cost_floor 钩子，17 号蟑螂守厨房先例；
        #     引擎本就按房间怪物数 +1，钩子抬高下限）；被晕的不拦。
        #   · 嘲讽攻击（p142）：斯芬克斯以理智攻击（目标理智防御、精神伤害），
        #     它输了对决不受伤也不被晕（on_monster_turn_attack 全权接管）。
        #   · 胜负（p71/p142）：英雄胜 = 解开谜语；叛徒胜 = 解开谜语或英雄
        #     全灭。叛徒出局时斯芬克斯继续守谜，吸收兜底（7/8 号口径）。
        #   已知简化：英雄知识攻击斯芬克斯（解谜攻击）与多只同时知识战未建模
        #     （引擎无玩家攻击属性选择层）；沙偶重生未建模；斯芬克斯"不进
        #     有英雄的房间"未建模（bot 守门厅不主动追击）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "sphinx_riddle",
        "traitor_rule": "revealer",
        "hero_goal": "在垃圾房/游戏室/管风琴房各拿一条线索，回作祟房做知识 6+ 解开谜语。",
        "traitor_goal": "抢先解开谜语（知识 5+），或让斯芬克斯拖死所有英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["entrance_hall", "junk_room", "game_room", "organ_room"],
        "tokens": ["sphinx", "clue_might", "clue_speed", "clue_sanity"],
        "setup": {
            "tracks": {"riddle": {"label": "谜语进度", "target": 3, "side": "heroes"}},
            "flags": {
                "clues": {},
                "riddle_solved": False,
            },
        },
        "monsters": [
            # spawn=deferred：只进 monster_specs，由 handler 全部放门厅
            {"template_id": "sphinx", "spawn": "deferred", "name": "斯芬克斯"},
        ],
        "actions": [
            {"id": "clue_junk", "side": "both", "label": "翻找垃圾（线索·力量）",
             "detail": "在垃圾房做力量 4+：成功获得一条线索（英雄成功后抽一张事件牌）"
                       "（p71/p142）。每回合只能尝试一条解谜检定。",
             "stat": "might", "target": 4, "rooms": ["junk_room"]},
            {"id": "clue_gameroom", "side": "both", "label": "整理游戏（线索·速度）",
             "detail": "在游戏室做速度 4+：成功获得一条线索（p71/p142）。",
             "stat": "speed", "target": 4, "rooms": ["game_room"]},
            {"id": "clue_organ", "side": "both", "label": "聆听音乐（线索·理智）",
             "detail": "在管风琴房做理智 4+：成功获得一条线索（p71/p142）。",
             "stat": "sanity", "target": 4, "rooms": ["organ_room"]},
            {"id": "solve_riddle", "side": "heroes", "label": "解开谜语",
             "detail": "集齐三条线索后在作祟房做知识 6+：成功即解开谜语、英雄获胜（p71）。",
             "stat": "knowledge", "target": 6},
            {"id": "traitor_solve_riddle", "side": "traitor", "label": "解开谜语",
             "detail": "集齐三条线索后在作祟房做知识 5+：成功即解开谜语、叛徒获胜（p142）。",
             "stat": "knowledge", "target": 5},
        ],
        "win_conditions": [],
        "source_pages": [71, 142],
    },
    61: {
        # 校准记录（2026-09-05，对照英雄手册 p72 / 叛徒手册 p143）：
        #   机制落在 EternalGloryMode：
        #   · 三遗物：雕像（画廊）/石棺（墓地）/古甲（酒窖）——强制入场
        #   · 矛 token 放作祟房间；幽灵战士（Speed 3 Might 5）生成并拾矛
        #   · 英雄拾矛 → 带到遗物房间 → 知识检定推 Track
        #   · Track = 2× 英雄数 且在两个不同房间 → 英雄胜
        #   · 矛离开遗物房间 → Track 归零
        #   · 英雄胜：安息；叛徒胜：英雄全灭
        #   简化：叛徒 incorporeal / 盾 / 偷矛需 3+ 伤害未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "ghost_warrior",
        "traitor_rule": "revealer",
        "hero_goal": "带着长矛到遗物房间说服幽灵战士安息。",
        "traitor_goal": "让幽灵战士杀死所有英雄。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": ["gallery", "graveyard", "wine_cellar"],
        "tokens": ["spear", "statue_relic", "sarcophagus_relic", "ancient_armor", "ghost_warrior"],
        "setup": {
            "tracks": {
                "persuasion_track": {"label": "说服进度", "target": 20, "side": "heroes"},
            },
            "flags": {
                "rest_tokens_rooms": [], "spear_held_by": None,
                "ghost_alive": True, "relic_rooms": {},
            },
        },
        "monsters": [
            {"template_id": "ghost", "name": "幽灵战士", "spawn": "deferred", "count": 1, "speed": 3, "might": 5, "sanity": 0},
        ],
        "actions": [
            {"id": "persuade_ghost", "side": "heroes", "label": "说服幽灵", "detail": "持矛在遗物房间做知识检定推 Track（p72）。", "stat": "knowledge", "target": 5, "progress": "persuasion_track"},
            {"id": "pick_up_spear", "side": "heroes", "label": "拾取长矛", "detail": "在同房间拾取幽灵战士掉落的长矛（p72）。"},
        ],
        "win_conditions": [],
        "source_pages": [72, 143],
    },
    62: {
        # 校准记录（2026-09-05，对照英雄手册 p73 / 叛徒手册 p144）：
        #   机制落在 BagOfTricksMode：
        #   · 叛徒角色从游戏中移除（p73）；疯子怪物（Speed 4 Might 3）生成
        #   · 英雄在同疯子/小玩意的房间做知识 6+ 推进进度
        #   · 进度 = 玩家数 → 疯子被送走（英雄胜）
        #   简化：小玩意收集/每房限一枚/灵应板加骰未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "bag_of_tricks",
        "traitor_rule": "revealer",
        "hero_goal": "在疯子杀死你们之前破解他的小玩意。",
        "traitor_goal": "让疯子收集足够的纪念品。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": ["madman_token"],
        "setup": {
            "tracks": {
                "trinket_progress": {"label": "小玩意破解", "target": "player_count", "side": "heroes"},
            },
            "flags": {"traitor_removed": True},
        },
        "monsters": [
            {"template_id": "madman", "name": "疯子（收藏家）", "spawn": "haunt_room", "count": 1, "speed": 4, "might": 3, "sanity": 0},
        ],
        "actions": [
            {"id": "tap_trinkets", "side": "heroes", "label": "破解小玩意", "detail": "在同疯子的房间做知识 6+（p73）。", "stat": "knowledge", "target": 6, "progress": "trinket_progress"},
        ],
        "win_conditions": [],
        "source_pages": [73, 144],
    },
    63: {
        # 校准记录（2026-09-05，对照英雄手册 p74 / 叛徒手册 p145）：
        #   机制落在 TwistingNetherMode：
        #   · 英雄锚定房间（知识 5+ 任意房间，每房一次）→ 玩家数个 → 英雄胜
        #   · 叛徒每回合溶解一个未锚定房间
        #   · 非锚定房间全溶 → 叛徒胜
        #   简化：nether 穿行/随机落房/重连房间/怪物不可攻击未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "twisting_nether",
        "traitor_rule": "revealer",
        "hero_goal": "锚定足够多的房间把房子拉回现实。",
        "traitor_goal": "溶解整栋房子。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": [],
        "setup": {
            "tracks": {
                "anchor_progress": {"label": "锚定进度", "target": "player_count", "side": "heroes"},
                "dissolve_progress": {"label": "溶解进度", "target": 50, "side": "traitor"},
            },
            "flags": {"anchored_rooms": [], "dissolved_rooms": []},
        },
        "monsters": [],
        "actions": [
            {"id": "anchor_room", "side": "heroes", "label": "锚定房间", "detail": "知识 5+ 锚定当前房间（p74）。", "stat": "knowledge", "target": 5, "progress": "anchor_progress"},
        ],
        "win_conditions": [],
        "source_pages": [74, 145],
    },
    64: {
        # 校准记录（2026-09-05，对照英雄手册 p75 / 叛徒手册 p146）：
        #   机制落在 BloodOfferingMode：
        #   · 女孩 token 放作祟房间；叛徒失去女孩卡
        #   · 邪教徒（英雄数-1）+ 蝙蝠（等同邪教徒数）布点
        #   · 计时到 7 → 恶魔不耐烦杀了叛徒（英雄胜）
        #   · 邪教徒到达女孩房间 → 献祭（叛徒胜）
        #   · 简化：女孩移动/蝙蝠精神免疫/钩爪未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "blood_offering",
        "traitor_rule": "revealer",
        "hero_goal": "保护女孩不被邪教徒献祭——撑到恶魔不耐烦为止。",
        "traitor_goal": "把女孩带到邪教徒面前献祭。",
        "suggested_monsters": ["cultist"],
        "required_cards": [],
        "key_rooms": [],
        "tokens": ["girl", "cultist", "bat"],
        "setup": {
            "tracks": {
                "demon_timer": {"label": "恶魔计时", "target": 7, "side": "heroes"},
            },
            "flags": {"girl_sacrificed": False},
        },
        "monsters": [
            {"template_id": "cultist", "name": "邪教徒", "spawn": "deferred", "count": 1, "speed": 3, "might": 4, "sanity": 4, "knowledge": 5},
            {"template_id": "bat", "name": "蝙蝠", "spawn": "deferred", "count": 1, "speed": 4, "might": 3, "sanity": 3},
        ],
        "actions": [],
        "win_conditions": [],
        "source_pages": [75, 146],
    },
    65: {
        # 校准记录（2026-09-05，对照英雄手册 p76 / 叛徒手册 p147）：
        #   机制落在 BreathOfWindMode：
        #   · 骚灵（ghost 模板，Speed 3）生成于作祟房间
        #   · 计时从 3 开始，每个怪物回合 -1；归零 → 英雄死亡
        #   · 找蜡烛：速度 3+（厨房/餐厅/教堂/画廊），每回合一次
        #   · 用蜡烛：弃蜡烛 + 知识 5+（作祟层）→ 放 token（每房一次）
        #   · 仪式 token 数 = 英雄数 → 英雄胜
        #   简化：骚灵免疫力量攻击/左轮/重生未建模。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "haunt_exorcism",
        "traitor_rule": "revealer",
        "hero_goal": "找蜡烛点燃仪式，在骚灵杀死你们之前驱逐它。",
        "traitor_goal": "让骚灵在仪式完成前杀死所有英雄。",
        "suggested_monsters": ["ghost"],
        "required_cards": [],
        "key_rooms": ["kitchen", "dining_room", "chapel", "gallery"],
        "tokens": ["candle", "poltergeist"],
        "setup": {
            "tracks": {
                "poltergeist_timer": {"label": "骚灵倒计时", "target": 3, "side": "traitor"},
                "exorcism_progress": {"label": "驱魔进度", "target": "player_count", "side": "heroes"},
            },
            "flags": {"candle_rooms_used": [], "candles_found": 0},
        },
        "monsters": [
            {"template_id": "ghost", "name": "骚灵", "spawn": "haunt_room", "count": 1, "speed": 3, "might": 0, "sanity": 4},
        ],
        "actions": [
            {"id": "find_candle", "side": "heroes", "label": "寻找蜡烛", "detail": "速度 3+（厨房/餐厅/教堂/画廊）（p76）。", "stat": "speed", "target": 3, "rooms": ["kitchen", "dining_room", "chapel", "gallery"]},
            {"id": "burn_candle", "side": "heroes", "label": "点燃蜡烛", "detail": "弃蜡烛 + 知识 5+ 在作祟层放 token（每房一次）（p76）。", "stat": "knowledge", "target": 5, "progress": "exorcism_progress"},
        ],
        "win_conditions": [],
        "source_pages": [76, 147],
    },
    66: {
        # 校准记录（2026-09-09，对照英雄手册 p77 / 叛徒手册 p148）：
        #   机制落在 HellOnEarthMode：
        #   · 力量轨道从 0 起、上限 8；充能代替攻击（小教堂/图书馆/圣徽同房，理智 4–7 +1、8+ +2）
        #   · 持徽者本回合充能后可封闭当前房间（轨道 ≥1 时 -1，放封印令牌）
        #   · 只能用圣徽打恶魔领主：骰数 = 当前轨道，对方用理智防守；未胜过则无事发生
        #   · 封闭房打胜 → 驱逐、英雄胜；未封闭则击退或击晕（击晕扣开局英雄数格轨道）
        #   · 叛徒仍在场，不能拾取/偷窃圣徽；神秘电梯对双方都拒绝移动
        #   · 恶魔领主属性随人数：3p 3/5/3，4p 4/5/4，5p 5/6/5，6p 6/6/6
        #   已知简化：击退方向由 bot 固定策略（远离持徽英雄）；人类的击退/击晕选择未接 prompter；
        #               引擎每回合一次剧本行动，持徽者充能成功且轨道仍 ≥1 时立刻封闭当前房间。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "hell_on_earth",
        "traitor_rule": "revealer",
        "hero_goal": "在封闭房间用圣徽成功攻击并驱逐恶魔领主。",
        "traitor_goal": "让恶魔领主和叛徒杀死所有英雄。",
        "suggested_monsters": ["hell_demon_lord"],
        "required_cards": ["omen_holy_symbol"],
        "key_rooms": [],
        "tokens": ["seal"],
        "setup": {
            "tracks": {
                "holy_power": {"label": "圣徽力量", "target": 8, "side": "heroes", "value": 0},
            },
            "flags": {
                "sealed_rooms": [],
                "prayed_this_turn": None,
                "initial_hero_count": 0,
            },
        },
        "monsters": [
            {
                "template_id": "hell_demon_lord",
                "name": "恶魔领主",
                "spawn": "deferred",
                "count": 1,
            }
        ],
        "actions": [
            {
                "id": "charge_holy_symbol",
                "side": "heroes",
                "label": "为圣徽充能",
                "detail": "代替攻击：在小教堂、图书馆或圣徽所在房间做理智检定（p77）。4–7 +1，8+ +2，上限 8。",
            },
            {
                "id": "seal_room",
                "side": "heroes",
                "label": "封闭房间",
                "detail": "持徽者本回合已充能、轨道 ≥1 时，把当前房间封闭（p77）。",
            },
            {
                "id": "holy_symbol_attack",
                "side": "heroes",
                "label": "用圣徽攻击恶魔领主",
                "detail": "持徽、同房间、轨道 ≥1：掷轨道枚骰对领主理智。只有打赢才有效（p77）。",
            },
        ],
        "win_conditions": [],
        "source_pages": [77, 148],
    },
    67: {
        # 校准记录（2026-09-09，对照英雄手册 p78 / 叛徒手册 p149）：
        #   机制落在 StorybookTwistsMode：
        #   · 叛徒入定：不能移动/攻击/用物品，不能被攻击，属性不升不降
        #   · 英雄与叛徒同房可偷（含疯子/女孩/狗）；叛徒不阻挡离房
        #   · 同房知识+故事轨 ≥6 抽取任务（6 骰 0–12，已抽则顺延）
        #   · 完成任务数 = 开局英雄数，并活到故事轨到 7 → 英雄胜，否则悲伤结局
        #   · 猎蛛开局；女巫/恶龙由故事段落召唤；剧情转折用尸体令牌
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "storybook_twists",
        "traitor_rule": "revealer",
        "hero_goal": "完成与开局英雄人数相等的任务，并活到故事结束。",
        "traitor_goal": "让故事走到悲伤结局，或杀死所有英雄。",
        "suggested_monsters": ["story_spider"],
        "required_cards": [],
        "key_rooms": [],
        "tokens": ["story", "body", "twist", "witch", "dragon"],
        "setup": {
            "tracks": {
                "quests": {"label": "已完成的故事任务", "target": "hero_count", "side": "heroes", "value": 0},
                "story": {"label": "故事进度", "target": 7, "side": "traitor", "value": 0},
            },
            "flags": {"scenario_started": True},
        },
        "monsters": [
            {"template_id": "story_spider", "spawn": "deferred", "count": 1, "name": "猎蛛", "speed": 4, "might": 5, "sanity": 3},
            {"template_id": "story_witch", "spawn": "deferred", "count": 1, "name": "女巫", "speed": 3, "might": 4, "sanity": 5},
            {"template_id": "story_dragon", "spawn": "deferred", "count": 1, "name": "恶龙", "speed": 5, "might": 7, "sanity": 4},
        ],
        "actions": [
            {"id": "obtain_quest", "side": "heroes", "label": "寻找关键情节", "detail": "与入定的叛徒同房，知识加上故事进度达到 6+，抽取一个任务。"},
            {"id": "complete_quest", "side": "heroes", "label": "完成故事任务", "detail": "按已抽取任务的条件结算；完成数需达到开局英雄人数。"},
            {"id": "steal_from_traitor", "side": "heroes", "label": "从入定者身上偷取", "detail": "代替攻击：与叛徒同房时自动偷走一件物品（含疯子、女孩、狗）。"},
            {"id": "plot_twist", "side": "traitor", "label": "剧情转折", "detail": "花费一枚尸体令牌，发动一次尚未用过的剧情转折。"},
        ],
        "win_conditions": [],
        "source_pages": [78, 149],
    },
    68: {
        # 精修 v3（M10-12）：对照英雄手册 p79 / 叛徒手册 p150 逐字重写，
        # 逻辑落在 haunt_modes.LabyrinthEscapeMode。骨架时代的 h68_hero_task /
        # h68_traitor_task 双任务轨是占位假机制（原文里叛徒根本不做检定，
        # 只是每回合推轨掷骰），已整段替换。
        #   · 布点（p150）：地下墓穴移出本局；英雄数枚钥匙（五边形令牌）与
        #     「英雄数-1」只仆人（速4/力3/智5）放进已探索房间；回合/伤害轨归零。
        #   · 逃脱（p79）：把「英雄数」枚钥匙全部带进入口大厅 → 厅里的英雄做
        #     知识 5+ 开锁；成功者抽一张事件牌并结束回合。门开后再进大厅的
        #     英雄花 2 点移动逃出，逃出者移出对局、不能返回。
        #   · 胜负（p79/p150）：逃出人数达到「作祟开始时活着的英雄数的一半」
        #     → 英雄胜；叛徒回合开始把轨 +1 后掷等于新位数的骰，总和 6+ →
        #     迷宫自我封闭 → 叛徒胜；或死亡英雄超过一半 → 叛徒胜。
        #   · 钥匙（p150）：叛徒既不能拾取也不能抢夺钥匙。
        #   · 迷乱（p150）：仆人可改用理智攻击——双方都不掉属性，但打赢就把一枚
        #     神志检定令牌放到该英雄身上；叛徒可在她回合内逼她白走一格（不花移动
        #     点），回合结束解除迷乱。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "labyrinth_escape",
        "traitor_rule": "revealer",
        "hero_goal": "收齐钥匙打开入口大厅的前门，让至少一半英雄逃出去。",
        "traitor_goal": "在迷宫自我封闭前杀死超过一半英雄——但你碰不到钥匙。",
        "suggested_monsters": [],
        "required_cards": [],
        # key_rooms / actions.rooms 一律留空：它们是机器人的常驻寻路目标，
        # 而本剧本的目标要看"手里有没有钥匙""门开没开"（见 handoff §6 第 6 条）。
        "key_rooms": [],
        "tokens": ["key", "confused"],
        "setup": {
            # 回合/伤害轨的真实位数记在 flags["turn_position"]（引擎轨道会被
            # target 封顶，56 号同款）；UI 轨只做 1..12 的刻度显示。
            "tracks": {
                "labyrinth_turn": {"label": "回合/伤害轨（迷宫封闭倒计时）", "target": 12, "side": "traitor"},
            },
            "flags": {
                "scenario_started": True,
                "hero_count": 0,
                "keys_total": 0,
                "escape_target": 0,
                "turn_position": 0,
                "door_unlocked": False,
                "sealed": False,
                "escaped_hero_ids": [],
            },
        },
        "monsters": [
            {"template_id": "labyrinth_servant", "spawn": "deferred", "count": 1,
             "name": "迷宫仆人", "speed": 4, "might": 3, "sanity": 5},
        ],
        "actions": [
            # 顺序即机器人的优先级（同分时取列表靠前者）：能逃就先逃，
            # 其次开锁，再次捡钥匙，最后才是倒手。房间与持物限制由 handler 把关。
            {"id": "flee_labyrinth", "side": "heroes", "label": "逃出迷宫",
             "detail": "门已开、人站在入口大厅时消耗 2 点移动逃出这栋房子："
                       "你被移出对局且再也回不来（p79）。",
             "requires_flags": {"door_unlocked": True}},
            {"id": "unlock_door", "side": "heroes", "label": "试着转动钥匙",
             "detail": "所有钥匙都在入口大厅里的英雄手上时，任何厅内英雄做知识 5+ "
                       "检定找出正确的开锁顺序；成功后你抽一张事件牌并结束回合（p79）。",
             "stat": "knowledge", "target": 5, "set_flags": {"door_unlocked": True}},
            {"id": "grab_key", "side": "heroes", "label": "拿起钥匙",
             "detail": "收走本房间的一枚钥匙。钥匙像物品一样可以拾取、放下、"
                       "交易和抢夺，但不能由狗携带（p79）。"},
            # 标签刻意避开"交给/交出"：bot 的行动打分给这两个词 +20，
            # 会让"转手"压过"拿起钥匙"和"试着转动钥匙"。
            {"id": "pass_key", "side": "heroes", "label": "把钥匙转交队友",
             "detail": "把钥匙转交给同房间里还缺一把钥匙的英雄（p79：钥匙可交易）。"},
            {"id": "drop_key", "side": "heroes", "label": "放下钥匙",
             "detail": "把钥匙留在当前房间（p79）。"},
        ],
        "win_conditions": [],
        "source_pages": [79, 150],
    },
    69: {
        # 校准记录（2026-09-10，对照英雄手册 p80 / 叛徒手册 p151）：
        #   骨架原本是"捕捉小精灵"假机制（h69_hero_task/traitor_task 进度轨）。
        #   机制落在 WispCaptureMode：
        #   · 开局（p151）：叛徒角色**移出游戏**（是设计不是失败——handler
        #     吸收"叛徒死→英雄胜"兜底）；小精灵（Speed 5 / Might 6 / Sanity 6）
        #     放作祟房；地下室楼梯未发现则取出放好；**小精灵先手**（轨道起点 1）。
        #   · 小精灵回合（p151）：回合开始轨道 +1 并清除全部孢子；然后不能
        #     停止移动（耗尽 5 点或死路为止）；离开的房间留孢子；不能进入
        #     已有孢子的房间；不主动攻击（防守反击照常）。
        #   · 孢子迷雾（p80）：英雄每回合**第一次**离开有孢子的房间做理智
        #     检定：6+ 本回合免疫、2-5 本回合剩余每次多花 1 点移动、0-1 回合
        #     立即结束（实现在 movement_cost_floor 钩子）。
        #   · 捕捉（p80）：与小精灵同房做知识 4+，成功 +1 枚捕捉令牌；累计
        #     作祟开始时英雄数枚 → 抓住小精灵 → 英雄胜。
        #   · 胜负（p80/p151）：轨道到 6 小精灵仍自由 → 叛徒胜；捕捉令牌满
        #     → 英雄胜。
        #   已知简化：小精灵探索新房间未建模；禁用神秘电梯/煤槽向上/坍塌房、
        #     屏障房两侧留孢子、免疫左轮（按属性免疫会误伤徒手速度攻击）、
        #     "先手"仅以轨道起点 1 体现（未改引擎回合顺序）。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "wisp_capture",
        "traitor_rule": "revealer",
        "hero_goal": "追上小精灵并累计英雄数枚捕捉令牌（各人知识 4+），在轨道到 6 前抓住它。",
        "traitor_goal": "作为小精灵躲到逃脱轨道走到 6，或让英雄全灭。",
        "suggested_monsters": [],
        "required_cards": [],
        "key_rooms": [],
        "tokens": ["wisp", "spore", "knowledge_check"],
        "setup": {
            # 逃脱轨道：flags["wisp_track"] 记真实值，此轨道封顶显示
            "tracks": {
                "capture_tokens": {"label": "捕捉进度", "target": 6, "side": "heroes"},
                "escape_track": {"label": "逃脱轨道", "target": 6, "side": "traitor"},
            },
            "flags": {
                "wisp_track": 1,
                "spore_rooms": [],
                "spore_state": {},
                "traitor_removed": True,
            },
        },
        "monsters": [
            # spawn=deferred：只进 monster_specs，由 handler 放作祟房
            {"template_id": "wisp", "spawn": "deferred", "name": "小精灵"},
        ],
        "actions": [
            {"id": "catch_wisp", "side": "heroes", "label": "捕捉小精灵",
             "detail": "与小精灵同房间时做知识 4+ 检定：每成功一次 +1 枚捕捉令牌，"
                       "英雄们累计到作祟开始时的英雄数枚即抓住它、英雄获胜（p80）。"
                       "每回合一次。",
             "stat": "knowledge", "target": 4, "progress": "capture_tokens",
             "requires": ["same_room:wisp"]},
        ],
        "win_conditions": [],
        "source_pages": [80, 151],
    },
    70: {
        # 校准记录（2026-09-10，对照英雄手册 p81 / 叛徒手册 p152）：
        #   骨架原本是"准备正确武器"假机制（h70 任务 + 进度轨）。
        #   机制落在 InhumanTransformationMode：
        #   · 开局（p152）：叛徒丢弃全部物品/预兆（保留 Bite）、物理属性恢复
        #     起始值；形态随机秘密选定（吸血鬼/狼人/蜘蛛），只写进 flags。
        #   · 转变（p152）：吸血鬼访问墓穴/墓地/血腥房间 + 力量攻击造成 ≥1
        #     物理伤害（吸血）；狼人访问阳台/塔楼/天井/花园/墓地；
        #     蜘蛛访问炭化房/温室/吱呀走廊/雕像走廊/神秘电梯。进入即计入。
        #   · 免疫（p81/p152）：叛徒只被克制武器伤害——attack_allowed 拦下
        #     其余全部攻击（吸血鬼=蘸圣水的矛/斧/血匕首；狼人=银弹+左轮；
        #     蜘蛛=杀虫剂，走行动免掷骰直接胜）。
        #   · 英雄备武器（p81）：圣水（礼拜堂/酒窖/地下湖 + 圣徽/天使羽毛，
        #     理智 ≥ 玩家人数）→ 蘸武器代替攻击；银弹（熔炉房/各实验室，
        #     知识 ≥ 玩家人数，仅一次）+ 左轮（已开金库搜线索）；杀虫剂三
        #     材料（醋/园艺工具/喷枪，搜索代替攻击）+ 知识 ≥ 玩家人数合成。
        #   · 干扰令牌（p152）：叛徒用匹配形态能力（理智/知识/力量令牌），
        #     英雄下回合对应属性 4+ 挣脱，否则回合立即结束。
        #   · 胜负（p81/p152）：英雄胜 = 用克制武器击败叛徒（通用兜底）；
        #     叛徒胜 = 完成转变或英雄全灭。
        #   已知简化：德鲁伊符不在卡库（圣水需圣徽/天使羽毛）；左轮位置简化
        #     为直接放 Vault；叛徒不可持物未在物品层拦截；物理属性恢复起始值
        #     （原文对全场最低者另有提升）；令牌用 flags 记账。
        "version": 3,
        "fidelity": "refined",
        "status": "playable",
        "mode": "inhuman_transformation",
        "traitor_rule": "revealer",
        "hero_goal": "查明他正在变成什么，备好克制它的武器（圣水武器/银弹左轮/杀虫剂），"
                     "在他完成转变前击败他。",
        "traitor_goal": "秘密完成属于你的转变——访遍对应的房间（吸血鬼还要吸到血），"
                        "或杀光所有英雄。",
        "suggested_monsters": [],
        "required_cards": ["item_revolver", "item_axe", "item_blood_dagger"],
        "key_rooms": [
            "crypt", "graveyard", "bloody_room", "balcony", "tower", "patio",
            "garden", "charred_room", "conservatory", "creaky_hallway",
            "statuary_corridor", "mystic_elevator", "chapel", "wine_cellar",
            "underground_lake", "furnace_room", "research_laboratory",
            "operating_laboratory", "kitchen", "larder", "attic", "junk_room",
        ],
        "tokens": ["holy_seal", "silver_bullets", "bug_spray"],
        "setup": {
            "tracks": {"form_visits": {"label": "转变访点", "target": 5, "side": "traitor"}},
            "flags": {
                "form": "vampire",
                "visited": [],
                "blood_drawn": False,
                "holy_rooms": [],
                "holy_weapons": [],
                "silver_bullets": False,
                "bug_spray": False,
                "ingredients": [],
                "tokens": {},
                "transformed": False,
            },
        },
        "monsters": [],
        "actions": [
            {"id": "create_holy_water", "side": "heroes", "label": "制作圣水",
             "detail": "在礼拜堂/酒窖/地下湖，且持有圣徽或天使羽毛时做理智检定："
                       "结果 ≥ 玩家人数即成功，该房间出现圣水（p81）。每回合一次。",
             "stat": "sanity", "target": 4,
             "rooms": ["chapel", "wine_cellar", "underground_lake"]},
            {"id": "dip_weapon", "side": "heroes", "label": "蘸水",
             "detail": "在有圣水的房间持有矛/斧/血匕首时，把武器浸入圣水"
                       "（代替攻击）：该武器从此可以伤害吸血鬼（p81）。",
             "stat": "might", "target": 0},
            {"id": "create_silver_bullets", "side": "heroes", "label": "铸造银弹",
             "detail": "在熔炉房/研究实验室/手术实验室做知识检定：结果 ≥ 玩家人数"
                       "即成功，造出银弹（全局仅一次，p81）。每回合一次。",
             "stat": "knowledge", "target": 4,
             "rooms": ["furnace_room", "research_laboratory", "operating_laboratory"]},
            {"id": "search_revolver", "side": "heroes", "label": "搜寻左轮线索",
             "detail": "在金库（须已开）搜出左轮——原文由叛徒从物品牌堆取出放置（p81）。",
             "stat": "knowledge", "target": 0, "rooms": ["vault"]},
            {"id": "search_ingredient", "side": "heroes", "label": "搜索材料",
             "detail": "在厨房/储藏室（醋）、花园/天井（园艺工具）、阁楼/垃圾房"
                       "（喷枪）搜索材料，代替攻击（p81）。",
             "stat": "knowledge", "target": 0,
             "rooms": ["kitchen", "larder", "garden", "patio", "attic", "junk_room"]},
            {"id": "assemble_bug_spray", "side": "heroes", "label": "调配杀虫剂",
             "detail": "集齐醋、园艺工具、喷枪后做知识检定：结果 ≥ 玩家人数即"
                       "合成杀虫剂（p81）。每回合一次。",
             "stat": "knowledge", "target": 4},
            {"id": "spray_traitor", "side": "heroes", "label": "喷洒杀虫剂",
             "detail": "持杀虫剂与叛徒同房间时使用，无需掷骰：若他是祸害蜘蛛，"
                       "英雄立即获胜（p81）。每回合一次。",
             "stat": "knowledge", "target": 0, "requires": ["same_room:traitor"]},
            {"id": "token_hypnotize", "side": "traitor", "label": "催眠（吸血鬼）",
             "detail": "吸血鬼形态专用：给同房英雄放一枚理智令牌（代替攻击），"
                       "该英雄下回合理智 4+ 否则回合结束（p152）。",
             "stat": "sanity", "target": 0},
            {"id": "token_infect", "side": "traitor", "label": "感染（狼人）",
             "detail": "狼人形态专用：给同房英雄放一枚知识令牌（代替攻击），"
                       "该英雄下回合知识 4+ 否则回合结束（p152）。",
             "stat": "knowledge", "target": 0},
            {"id": "token_trap", "side": "traitor", "label": "结网（蜘蛛）",
             "detail": "祸害蜘蛛形态专用：给同房英雄放一枚力量令牌（代替攻击），"
                       "该英雄下回合力量 4+ 否则回合结束（p152）。",
             "stat": "might", "target": 0},
        ],
        "win_conditions": [],
        "source_pages": [81, 152],
    },
}


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
        # 只补「英雄全灭→叛徒胜」这一条通用兜底。**不补**「叛徒死亡→英雄胜」：
        # 基础规则是"先完成剧本目标的一方获胜；即使叛徒死亡，只要怪物还能完成
        # 目标就照常行动"，叛徒死并不自动等于英雄达成目标。这条隐藏默认历史上
        # 让 #1 木乃伊（叛徒死后木乃伊照常行动）在叛徒阵亡时误判英雄胜。
        # 需要"叛徒死→英雄胜"的剧本必须在自己 handler / win_conditions 里显式声明。
        normalized.setdefault(
            "win_conditions",
            [
                {
                    "winner": "traitor",
                    "type": "all_heroes_dead",
                    "reason": normalized.get("traitor_goal", "所有英雄都倒下了。"),
                },
            ],
        )
    return normalized
