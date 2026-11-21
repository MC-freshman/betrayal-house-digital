#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Widow's Walk 扩展内容（run5 隔离存档，**默认不激活**）。

为什么存在
----------
run5 的验收对象是桌面端 P 表的 **142 个资源位**（角色 12 / 房间 50 / 事件 45 /
物品 22 / 预兆 13）。Widow's Walk（WW）扩充的 20 屋顶房 + 15 事件 + 10 物品 +
5 预兆 + 50 剧本（槽位 71-120）不属于本轮范围，但**已完成的建模不删除**，
统一迁到本模块保存。

边界（.codebuddy/wfat/run5_acceptance_criteria.md §1.2）
--------------------------------------------------------
* ``content.py`` 只保留 142 位对应内容；本模块不被 ``content.py`` 导入。
* 任何生产模块都不得 ``import content_ww``（A-29 判据 5/6）。
* ``haunts/_ww_deferred/`` 与 ``haunts_zh/_ww_deferred/`` 保存 50 本 WW 剧本的
  handler 与中文手册；``assets_ww/placeholders/`` 保存 50 张 WW 占位图。
  三者都不被 pipeline / registry / build 扫描。

如何重新激活
------------
显式 ``import content_ww`` 后调用 ``activate()``：把 WW 集合挂回 ``content``
模块（就地追加，不重建对象），随后 ``content.build_catalog()`` 即可看到 192 位。
本轮不调用、不测试。

内容来源
--------
隔离自 ``content.py`` / ``haunt_rules.py``（run5 S0 归档
``_freeze/content_pre_run5.py``，sha256=7138f310dd14ac86a41210c1f2be42c791fb7ff619530eb51fd53b5419d160f6；id 集合相等性见
``qa/run5_ww_isolation.json``）。官方资料：``.codebuddy/wfat/ww_official_content.json``。
"""

from __future__ import annotations

try:  # 包内导入（game.content）
    from .content import card_def, monster_def, room_def
    from .content import HAUNT_NAMES as BASE_HAUNT_NAMES
    from .haunt_rules import _make_scenario_rule
except ImportError:  # 直接脚本 / game 目录在 sys.path 上（asset_pipeline 的用法）
    from content import card_def, monster_def, room_def  # type: ignore
    from content import HAUNT_NAMES as BASE_HAUNT_NAMES  # type: ignore
    from haunt_rules import _make_scenario_rule  # type: ignore


# ----------------------------------------------------------------------
# 楼层：屋顶层（WW 新楼层，独立字符串值，避免与 -1/0/1 的算术假设冲突）
# ----------------------------------------------------------------------
FLOOR_ROOF = "roof"


# ======================================================================
# 1) 预兆 5 张（官方 8 张里按 P 表硬指标落位 5 张）
# ======================================================================
WW_OMEN_ADDITIONS = [
    card_def(
        card_id="omen_bloodstone",
        kind="omen",
        name="血岩",
        source_name="Bloodstone",
        text="握紧这块温热的石头，愤怒便有了形状。",
        tags=("omen", "attack_bonus"),
        effect_id="omen_bloodstone",
        keep=True,
        bonus={"attack": 1},
    ),
    card_def(
        card_id="omen_box",
        kind="omen",
        name="盒子",
        source_name="Box",
        text="盒子很轻，里面的东西却在移动。",
        tags=("omen", "omen_key"),
        effect_id="omen_box",
        keep=True,
        bonus={"might": 1},
    ),
    card_def(
        card_id="omen_key",
        kind="omen",
        name="钥匙",
        source_name="Key",
        text="这把钥匙不属于这栋房子里的任何一把锁。",
        tags=("omen", "knowledge_bonus"),
        effect_id="omen_key",
        keep=True,
        bonus={"knowledge": 1},
    ),
    card_def(
        card_id="omen_photograph",
        kind="omen",
        name="照片",
        source_name="Photograph",
        text="照片里的人站在你从未见过的房间门前。",
        tags=("omen", "sanity_bonus"),
        effect_id="omen_photograph",
        keep=True,
        bonus={"sanity": 1},
    ),
    card_def(
        card_id="omen_vial",
        kind="omen",
        name="小瓶",
        source_name="Vial",
        text="瓶中的液体随着你的心跳明灭。",
        tags=("omen", "attack_bonus"),
        effect_id="omen_vial",
        keep=True,
        bonus={"attack": 1},
    ),
]

# ======================================================================
# 2) 物品 10 张（官方 11 张，Dynamite 与基础版重名不重复登记）
# ======================================================================
WW_ITEM_ADDITIONS = [
    card_def(
        card_id="item_blueprint",
        kind="item",
        name="宅邸蓝图",
        source_name="Blueprint",
        text="蓝图标注了哑侍井道的走向，让移动与检定更有把握。",
        tags=("item", "knowledge_bonus"),
        effect_id="item_reroll",
    ),
    card_def(
        card_id="item_left_hand",
        kind="item",
        name="断手",
        source_name="The Left Hand",
        text="这只冰冷的左手会在你出手时悄然借力。",
        tags=("item", "attack_bonus"),
        effect_id="omen_mask",
        bonus={"attack": 1},
    ),
    card_def(
        card_id="item_signal_whistle",
        kind="item",
        name="信号哨",
        source_name="Signal Whistle",
        text="尖利的哨声会把屋里的东西引过来——用的时候想清楚。",
        tags=("item", "lure"),
        effect_id="item_bell",
    ),
    card_def(
        card_id="item_lockpicks",
        kind="item",
        name="撬锁工具",
        source_name="Lockpicks",
        text="对付上锁的房间正合适。",
        tags=("item", "knowledge_bonus", "reroll"),
        effect_id="item_reroll",
    ),
    card_def(
        card_id="item_storm_lantern",
        kind="item",
        name="风灯",
        source_name="Storm Lantern",
        text="风雨夜里，这盏灯是唯一让人安心的光。",
        tags=("item", "sanity_bonus"),
        effect_id="item_storm_lantern",
        bonus={"sanity": 1},
    ),
    card_def(
        card_id="item_ghost_camera",
        kind="item",
        name="灵异相机",
        source_name="Ghost Camera",
        text="冲洗出来的照片总比取景时多一个人。",
        tags=("item", "draw"),
        effect_id="item_puzzle_box",
        data={"draw_items": 1},
    ),
    card_def(
        card_id="item_bird_cage",
        kind="item",
        name="空鸟笼",
        source_name="Bird Cage",
        text="笼门开着，笼底的羽毛还是新的。",
        tags=("item", "knowledge_bonus"),
        effect_id="item_bird_cage",
        bonus={"knowledge": 1},
    ),
    card_def(
        card_id="item_sewing_kit",
        kind="item",
        name="针线包",
        source_name="Sewing Kit",
        text="缝好伤口，也缝好衣裳。",
        tags=("item", "heal"),
        effect_id="item_heal_small",
        data={"kind": "physical", "heal": 1},
    ),
    card_def(
        card_id="item_weather_vane",
        kind="item",
        name="风向标",
        source_name="Weather Vane",
        text="它指的方向，从来不是风的方向。",
        tags=("item", "reroll"),
        effect_id="item_reroll",
    ),
    card_def(
        card_id="item_preserved_specimen",
        kind="item",
        name="保存标本",
        source_name="Preserved Specimen",
        text="福尔马林里泡着的东西，最好别细看。",
        tags=("item", "might_bonus"),
        effect_id="item_preserved_specimen",
        bonus={"might": 1},
    ),
]

# ======================================================================
# 3) 事件 15 张（事件位 45→60 超出部分；effect_id 复用基础事件效果）
# ======================================================================
WW_EVENT_ADDITIONS = [
    ("event_contract", "契约", "Contract", "event_disquieting_sounds"),
    ("event_roof_wind", "屋顶之风", "Roof Wind", "event_smoke"),
    ("event_dumbwaiter_stall", "哑侍卡住", "Dumbwaiter Stall", "event_whoops"),
    ("event_creaking_rafter", "吱呀椽木", "Creaking Rafter", "event_disquieting_sounds"),
    ("event_mirror_glint", "镜面反光", "Mirror Glint", "event_bloody_vision"),
    ("event_dust_and_ash", "尘与灰", "Dust and Ash", "event_grave_dirt"),
    ("event_attic_bats", "阁楼蝙蝠", "Attic Bats", "event_creepy_crawlies"),
    ("event_old_portrait", "旧肖像", "Old Portrait", "event_bloody_vision"),
    ("event_cellar_draft", "地窖穿堂风", "Cellar Draft", "event_something_slimy"),
    ("event_glass_shatter", "玻璃碎裂", "Glass Shatter", "event_whoops"),
    ("event_hidden_ledger", "隐藏账本", "Hidden Ledger", "event_something_hidden"),
    ("event_music_from_nowhere", "凭空乐声", "Music from Nowhere", "event_the_voice"),
    ("event_frozen_clock", "停摆的钟", "Frozen Clock", "event_night_view"),
    ("event_bird_attack", "群鸟袭人", "Bird Attack", "event_spider"),
    ("event_the_left_hand_writes", "左手书写", "The Left Hand Writes", "event_bloody_vision"),
]

# ----------------------------------------------------------------------
# Widow's Walk 屋顶层房间（20 块官方扩充板块）
# ----------------------------------------------------------------------
# 数据来源：.codebuddy/wfat/ww_official_content.json §rooms（官方 20 块板块：
# Roof Landing / Arsenal / Bathroom / Cave / Drawing Room / Dungeon / Laundry /
# Locked Room / Menagerie / Nursery / Panic Room / Rookery / Sewing Room /
# Solarium / Spiral Staircase / Storm Cellar / Study / Theater / Tree House /
# Widow's Walk）。
#
# 建模说明（ww_architecture 决策：屋顶层用双面板块机制的简化抽象）：
# * floor 一律记 FLOOR_ROOF：官方 20 块板块为双面（普通面 + roof/upper 面），
#   "屋顶探索从 20 块板块池抽取"即 WW-T01 的 20 屋顶房池；每块的正反面
#   归属需板块扫描核对，这里统一按屋顶房池建模。
# * id "ww_bathroom"：官方 Bathroom 板块与既有 ROOM_SUPPLEMENTAL_SPECS 的
#   bathroom（旧 142 行零漂移，不可改）同名。WW 板块以 ww_ 前缀区分，
#   效果与官方一致（无特殊效果 + 事件符号）。
# * doors：官方规则表不含门位数据（印在板块图上，需扫描核对），按房间
#   形态给 2-3 门占位，rotation 机制可自行旋转适配。
# * Roof Landing 开局即入局，通过 down 链接与 Upper Landing 互通（引擎
#   链接为双向自动发现，因此不必改动 upper_landing 的旧定义）。
ROOF_ROOMS = [
    {
        "id": "roof_landing",
        "name": "屋顶平台",
        "source_name": "Roof Landing",
        "floor": FLOOR_ROOF,
        "doors": ("south", "east", "west"),
        "symbol": None,
        "effect_id": "room_start_roof",
        "special": True,
        "links": {"down": "upper_landing"},
        "text": "屋顶层的起点，与二楼平台互通。",
    },
    {
        "id": "arsenal",
        "name": "军械库",
        "source_name": "Arsenal",
        "floor": FLOOR_ROOF,
        "doors": ("north", "east", "west"),
        "symbol": "item",
        "effect_id": "room_arsenal",
        "special": False,
        "links": {},
        "text": "在此房间抽物品卡时抽 2 张选 1 保留，弃另一张。",
    },
    {
        "id": "ww_bathroom",
        "name": "浴室",
        "source_name": "Bathroom (WW)",
        "floor": FLOOR_ROOF,
        "doors": ("north", "south"),
        "symbol": "event",
        "effect_id": "room_bathroom",
        "special": False,
        "links": {},
        "text": "Widow's Walk 板块浴室：无特殊效果，首次进入按事件符号抽牌。",
    },
    {
        "id": "cave",
        "name": "洞穴",
        "source_name": "Cave",
        "floor": FLOOR_ROOF,
        "doors": ("north", "east"),
        "symbol": "event",
        "effect_id": "room_cave",
        "special": False,
        "links": {},
        "text": "洞穴深处寒气逼人：进入时进行力量检定（目标 4），失败失去 1 点力量。",
    },
    {
        "id": "drawing_room",
        "name": "会客厅",
        "source_name": "Drawing Room",
        "floor": FLOOR_ROOF,
        "doors": ("north", "east", "south"),
        "symbol": None,
        "effect_id": "room_drawing_room",
        "special": False,
        "links": {},
        "text": "发现时从任意牌堆抽 1 张牌。",
    },
    {
        "id": "dungeon",
        "name": "地牢",
        "source_name": "Dungeon",
        "floor": FLOOR_ROOF,
        "doors": ("north", "south", "west"),
        "symbol": "omen",
        "effect_id": "room_dungeon",
        "special": False,
        "links": {},
        "text": "进入时须过理智检定（目标 3），失败失去 1 点理智。",
    },
    {
        "id": "laundry",
        "name": "洗衣房",
        "source_name": "Laundry Room",
        "floor": FLOOR_ROOF,
        "doors": ("south", "east"),
        "symbol": "item",
        "effect_id": "room_laundry",
        "special": False,
        "links": {},
        "text": "回合结束时弃 1 张物品卡，可从物品弃牌堆抽 1 张。",
    },
    {
        "id": "locked_room",
        "name": "上锁的房间",
        "source_name": "Locked Room",
        "floor": FLOOR_ROOF,
        "doors": ("north", "west"),
        "symbol": "event",
        "effect_id": "room_locked_room",
        "special": False,
        "links": {},
        "text": "每扇门都挂着锁：进入时进行知识检定（目标 3），失败被锁在门外受 1 点精神伤害并停下。",
    },
    {
        "id": "menagerie",
        "name": "动物笼舍",
        "source_name": "Menagerie",
        "floor": FLOOR_ROOF,
        "doors": ("south", "west"),
        "symbol": "event",
        "effect_id": "room_menagerie",
        "special": False,
        "links": {},
        "text": "每局一次：结束回合在这里可获得 1 点力量。",
    },
    {
        "id": "nursery",
        "name": "育儿室",
        "source_name": "Nursery",
        "floor": FLOOR_ROOF,
        "doors": ("north", "south", "east"),
        "symbol": "omen",
        "effect_id": "room_nursery",
        "special": False,
        "links": {},
        "text": "结束回合在这里：理智低于起始值 +1，高于起始值 -1。",
    },
    {
        "id": "panic_room",
        "name": "安全室",
        "source_name": "Panic Room",
        "floor": FLOOR_ROOF,
        "doors": ("east", "west"),
        "symbol": "event",
        "effect_id": "room_panic_room",
        "special": False,
        "links": {},
        "text": "离开时可行速度检定（目标 3），成功立即移动到任意楼梯口。",
    },
    {
        "id": "rookery",
        "name": "鸦舍",
        "source_name": "Rookery",
        "floor": FLOOR_ROOF,
        "doors": ("north", "east", "south"),
        "symbol": "omen",
        "effect_id": "room_rookery",
        "special": False,
        "links": {},
        "text": "发现时搜检房间板块堆，把其中 1 块放进房屋。",
    },
    {
        "id": "sewing_room",
        "name": "缝纫室",
        "source_name": "Sewing Room",
        "floor": FLOOR_ROOF,
        "doors": ("north", "east"),
        "symbol": "item",
        "effect_id": "room_sewing_room",
        "special": False,
        "links": {},
        "text": "结束回合在这里可弃 1 张物品卡：若力量低于起始值则 +1。",
    },
    {
        "id": "solarium",
        "name": "日光室",
        "source_name": "Solarium",
        "floor": FLOOR_ROOF,
        "doors": ("south", "east", "west"),
        "symbol": "item",
        "effect_id": "room_solarium",
        "special": False,
        "links": {},
        "text": "结束回合在这里可弃 1 张物品卡获得 1 点理智。",
    },
    {
        "id": "spiral_staircase",
        "name": "螺旋楼梯",
        "source_name": "Spiral Staircase",
        "floor": FLOOR_ROOF,
        "doors": ("west", "east"),
        "symbol": None,
        "effect_id": "room_spiral_staircase",
        "special": False,
        "links": {},
        "text": "进入时可花 2 点移动移动到任意楼层的楼梯口。",
    },
    {
        "id": "storm_cellar",
        "name": "避风地窖",
        "source_name": "Storm Cellar",
        "floor": FLOOR_ROOF,
        "doors": ("north", "west"),
        "symbol": "item",
        "effect_id": "room_storm_cellar",
        "special": False,
        "links": {},
        "text": "Widow's Walk 板块避风地窖：无特殊效果，首次进入按物品符号抽牌。",
    },
    {
        "id": "study",
        "name": "书房",
        "source_name": "Study",
        "floor": FLOOR_ROOF,
        "doors": ("north", "south"),
        "symbol": "omen",
        "effect_id": "room_study",
        "special": False,
        "links": {},
        "text": "每局一次：结束回合在这里可获得 1 点精神属性。",
    },
    {
        "id": "theater",
        "name": "剧院",
        "source_name": "Theater",
        "floor": FLOOR_ROOF,
        "doors": ("east", "south", "west"),
        "symbol": "omen",
        "effect_id": "room_theater",
        "special": False,
        "links": {},
        "text": "Widow's Walk 板块剧院：无特殊效果，是多场作祟的舞台。",
    },
    {
        "id": "tree_house",
        "name": "树屋",
        "source_name": "Tree House",
        "floor": FLOOR_ROOF,
        "doors": ("north", "south"),
        "symbol": "event",
        "effect_id": "room_tree_house",
        "special": False,
        "links": {},
        "text": "树屋以枝干与上层连通：进入时可行速度检定（目标 3），成功移动到上层任意房间。",
    },
    {
        "id": "widows_walk",
        "name": "寡妇行",
        "source_name": "Widow's Walk",
        "floor": FLOOR_ROOF,
        "doors": ("north", "east", "south", "west"),
        "symbol": "event",
        "effect_id": "room_widows_walk",
        "special": False,
        "links": {},
        "text": "高处的环形回廊：在此进行知识检定 +1、速度检定 -1（最低 0）。",
    },
]

# 屋顶层房池的全部模板 id（引擎探索/作祟触发用它判断"房间来自屋顶层"）。
ROOF_ROOM_IDS = tuple(spec["id"] for spec in ROOF_ROOMS)

# Widow's Walk 新增事件张数：官方扩充含 11 张事件卡，按 P 表硬指标
# （事件位 45→60）落位 15 张，基础 45 张事件照旧全部保留。
WW_EVENT_ADDITION = 15

def _roof_room_def(spec: dict) -> dict:
    """把 ROOF_ROOMS 的 dict 规格展开为与 room_def 同构的房间模板。"""
    return room_def(
        room_id=spec["id"],
        name=spec["name"],
        source_name=spec["source_name"],
        floor=spec["floor"],
        doors=spec["doors"],
        symbol=spec["symbol"],
        effect_id=spec["effect_id"],
        text=spec.get("text", ""),
        special=spec.get("special", False),
        links=spec.get("links"),
        tags=("roof", "widows_walk"),
        generated=False,
    )


# ======================================================================
# 4) 剧本名 50 条（团队槽位 71-120 = 官方编号 51-100）
# ======================================================================
WW_HAUNT_NAMES = [
    (71, "Director's Cut"),
    (72, "Prism"),
    (73, "Till Morning Light"),
    (74, "Monster Mash"),
    (75, "She Is Not Amused"),
    (76, "Make America Disintegrate Again"),
    (77, "The Gathering Storm"),
    (78, "Olly Olly Oxen Free"),
    (79, "The Fleshchild's Alchemical Mandate"),
    (80, "Cat O'Clock"),
    (81, "Captain Sting's Revenge"),
    (82, "Rosencrantz and All of You Are Dead"),
    (83, "Shush"),
    (84, "Chairman of the Board"),
    (85, "Sushi Night"),
    (86, "The Cardinal Sins"),
    (87, "Murderball"),
    (88, "He Who Must Not Be Read"),
    (89, "No Noose is Good News"),
    (90, "To Reach the Cosmos"),
    (91, "The Other Side"),
    (92, "Man's Worst Enemy"),
    (93, "Existence Precedes Essence"),
    (94, "Coulrophobia"),
    (95, "Let It Glow"),
    (96, "Back to the Past"),
    (97, "They're Always After Me"),
    (98, "The Devil's Name"),
    (99, "The Twins"),
    (100, "I, Mutant"),
    (101, "The Canopic Curse"),
    (102, "Get a Clue"),
    (103, "In the Details"),
    (104, "Forget to Remember"),
    (105, "The Murderer in the Machine"),
    (106, "The Woods in the Cabin"),
    (107, "Sibling Rivalry"),
    (108, "Cry, Babylon!"),
    (109, "One of the Master's Affairs"),
    (110, "Internal Conflict"),
    (111, "Burn out the Darkness"),
    (112, "Ghost at the Finish Line"),
    (113, "Owl's Moving Castle"),
    (114, "Last Will and Tournament"),
    (115, "Nanny, Interrupted"),
    (116, "House of Leavings"),
    (117, "Lambs to the Slaughter"),
    (118, "Plastic Fantastic"),
    (119, "The Manor of Your Demise"),
    (120, "Let's Play a Game"),
]

# 完整 120 条（1-70 来自 content.py，71-120 为本模块新增）。
HAUNT_NAMES = list(BASE_HAUNT_NAMES) + list(WW_HAUNT_NAMES)


# ======================================================================
# 5) 怪物
# ======================================================================
# 实测结论（run5 S1，见 qa/run5_ww_isolation.json §monsters）：
# MONSTER_BASES 的 52 条**全部**被 1-70 号基础剧本引用（逐 id 反查 70 个
# handler 模块 0 命中缺失），因此 WW 没有可迁出的专属怪物；此处只留扩展点。
WW_MONSTER_ADDITIONS: list = []


# ======================================================================
# 6) WW 剧本规则表（原 haunt_rules.py 槽位 71-120）
# ======================================================================
# ----------------------------------------------------------------------
# Widow's Walk 剧本（槽位 71-120 = 官方编号 51-100）
# ----------------------------------------------------------------------
# 数据来源：.codebuddy/wfat/ww_official_content.json §haunts（官方剧本书
# Secrets of Survival / Traitor's Tome 的逐本提取）。
#
# 建模口径（ww_architecture 简化建模，engine_note 逐本登记）：
# * 骨架用 _make_scenario_rule 生成：双进度轨（hero_progress /
#   traitor_progress）+ 检定型剧本行动 + win_conditions。英雄胜利 = 轨道
#   推满（hero_progress >= player_count）；叛徒胜利 = 英雄全灭。官方的
#   竞速/计时/收集细则逐本精修时再换专属 mode。
# * 无叛徒剧本（77/103/112/119/120）与多叛徒剧本（71/84/99）按引擎单叛徒
#   模型降级：traitor_rule 给形式叛徒，胜负条件照常可判。
# * rooms = 官方触发房间映射到本仓库房间 id（WW 板块 id 见 content.py
#   ROOF_ROOMS，即"屋顶层条件剧本"）；required_cards 只列本仓库存在的卡，
#   官方预兆未落位的（Letter/Rope/Cat 等）不写进引擎关键牌，只留在
#   trigger_hint 叙述。
WW_SCENARIO_TABLE: dict[int, dict[str, Any]] = {
    71: dict(
        mode="ww_haunt_71", traitor_rule="revealer",
        hero_goal="拿到关键道具与《视觉》剧本，在剧院向吹毛求疵的导演们展示，让烂片杀青。",
        traitor_goal="扮演导演们，在英雄完成展示前把他们全部淘汰出局。",
        rooms=("theater",), tokens=(),
        hero_task="在剧院完成排练检定（多位叛徒时由形式叛徒轮替）",
        traitor_task="以检定给英雄挑刺，推进淘汰进度",
        hero_stat=("knowledge", "sanity"), hero_target=5,
        required_cards=("omen_book",),
        trigger_hint="官方触发：剧院 × 书/信/照片/戒指（官方 #51，多叛徒）",
        engine_note="官方多叛徒按单叛徒模型降级；《视觉》为官方事件卡（未落位），用知识/理智检定链近似。",
    ),
    72: dict(
        mode="ww_haunt_72", traitor_rule="revealer",
        hero_goal="实验结束时任一存活英雄抵达棱镜核心的出口房间。",
        traitor_goal="主持死亡监狱般的杀人机关，让所有英雄困死在棱镜里。",
        rooms=("gallery", "gymnasium", "junk_room", "servants_quarters"), tokens=(),
        hero_task="在机关房间完成破解检定，推进抵达出口的进度",
        traitor_task="以力量检定给机关加固，阻止英雄逃生",
        hero_stat=("knowledge", "speed"), hero_target=5,
        required_cards=("omen_box",),
        trigger_hint="官方触发：画廊/健身房/杂物间/仆人房 × 盒子（官方 #52）",
        engine_note="棱镜传送机关简化为双进度轨竞速。",
    ),
    73: dict(
        mode="ww_haunt_73", traitor_rule="revealer",
        hero_goal="存活到回合轨抵达 5（黎明到来）。",
        traitor_goal="开门放进杀人节暴徒 Surge，在黎明前杀光英雄。",
        rooms=("catacombs", "gallery", "kitchen"), tokens=(),
        hero_task="完成坚守检定，撑到天亮",
        traitor_task="以力量检定暴走，加快黑夜侵蚀",
        hero_stat=("might", "sanity"), hero_target=5,
        required_cards=("omen_key",),
        trigger_hint="官方触发：地下墓穴/画廊/厨房 × 钥匙（官方 #53，怪物 Surge）",
        engine_note="Surge 暴徒暂不生成（monsters 空），以叛徒检定节奏近似黑夜侵蚀。",
    ),
    74: dict(
        mode="ww_haunt_74", traitor_rule="revealer",
        hero_goal="按弱点驱逐不低于英雄数一半（向上取整）的经典怪物。",
        traitor_goal="作为不可攻击的舞会主人，召集怪物军团守住舞会。",
        rooms=("dining_room", "gallery", "master_bedroom", "servants_quarters"), tokens=(),
        hero_task="完成驱魔检定，推进驱逐进度",
        traitor_task="以检定为怪物助威，拖延驱逐",
        hero_stat=("sanity", "might"), hero_target=5,
        required_cards=("omen_medallion",),
        trigger_hint="官方触发：餐厅/画廊/主卧/仆人房 × 信（官方 #54，八怪物对应预兆弱点）",
        engine_note="八只官方怪物未生成，驱逐进度以英雄检定轨道近似。",
    ),
    75: dict(
        mode="ww_haunt_75", traitor_rule="highest_knowledge",
        hero_goal="先取得《镜中倒影》，再砍下美杜莎的头。",
        traitor_goal="化身美杜莎，把英雄逐一变成石像。",
        rooms=("dungeon",), tokens=(),
        hero_task="完成斩首检定（需先在镜中看清她）",
        traitor_task="以理智检定石化英雄",
        hero_stat=("might",), hero_target=5,
        required_cards=("omen_bloodstone", "omen_book"),
        trigger_hint="官方触发：地牢 × 血岩/书/女孩/面具（官方 #55，怪物 Statue/Hoplite）",
        engine_note="《镜中倒影》事件卡未落位，前置条件折算进英雄检定轨道。",
    ),
    76: dict(
        mode="ww_haunt_76", traitor_rule="revealer",
        hero_goal="在叛徒完成升格仪式（20 枚力量标记）前摧毁全部魂器。",
        traitor_goal="竞选总统的巫妖候选人：完成升格仪式并消灭所有英雄。",
        rooms=("dungeon", "rookery", "study", "theater"), tokens=(),
        hero_task="完成搜魂检定，摧毁魂器",
        traitor_task="以力量检定推进升格仪式",
        hero_stat=("knowledge", "might"), hero_target=5,
        required_cards=("omen_madman",),
        trigger_hint="官方触发：地牢/鸦舍/书房/剧院 × 疯子（官方 #56）",
        engine_note="20 枚 Power token 折算为双方进度轨。",
    ),
    77: dict(
        mode="ww_haunt_77", traitor_rule="revealer",
        hero_goal="用工具封住所有通往地下室的入口（地下层平台被毁则失败）。",
        traitor_goal="无叛徒：全员对抗逐渐摧毁房屋的风暴（形式叛徒只驱动风暴检定）。",
        rooms=("rookery",), tokens=(),
        hero_task="完成封堵检定，封住通往地下室的入口",
        traitor_task="以检定推进风暴对房屋的破坏",
        hero_stat=("might", "knowledge"), hero_target=5,
        required_cards=("omen_box",),
        trigger_hint="官方触发：鸦舍 × 盒子/猫/狗/面具（官方 #57，无叛徒；mega 前置）",
        engine_note="无叛徒剧本按引擎单叛徒模型降级；风暴破坏以叛徒轨道近似。",
    ),
    78: dict(
        mode="ww_haunt_78", traitor_rule="revealer",
        hero_goal="找到等于英雄数的娃娃，并在熔炉房把它们全部烧掉。",
        traitor_goal="被捉迷藏惨死小女孩之灵附身，阻止英雄烧掉娃娃。",
        rooms=("nursery", "rookery", "study", "theater"), tokens=(),
        hero_task="完成搜寻与焚烧检定，推进烧毁进度",
        traitor_task="以检定把娃娃藏得更深",
        hero_stat=("knowledge", "might"), hero_target=5,
        required_cards=("omen_girl",),
        trigger_hint="官方触发：育儿室/鸦舍/书房/剧院 × 女孩（官方 #58）",
        engine_note="Doll 令牌折算为英雄进度轨。",
    ),
    79: dict(
        mode="ww_haunt_79", traitor_rule="revealer",
        hero_goal="杀死炼金术师造出的血肉之子。",
        traitor_goal="血肉之子：为 Zosimus 收割英雄的血肉样本。",
        rooms=("catacombs", "furnace_room", "pentagram_chamber", "servants_quarters", "study"), tokens=(),
        hero_task="完成解剖检定，定位血肉之子的核心",
        traitor_task="以力量检定收割英雄样本",
        hero_stat=("might",), hero_target=5,
        required_cards=("omen_bloodstone",),
        trigger_hint="官方触发：地下墓穴/熔炉房/五芒星室/仆人房/书房 × 血岩（官方 #59）",
        engine_note="Fleshchild 怪物未生成，收割以叛徒轨道近似。",
    ),
    80: dict(
        mode="ww_haunt_80", traitor_rule="revealer",
        hero_goal="集齐猫粮材料（餐厅/厨房/笼舍）并以理智攻击说服 The Cat 进食。",
        traitor_goal="受猫意志支配者：放任 The Cat 与恶猫军团接管房屋。",
        rooms=("dining_room", "kitchen", "servants_quarters", "theater"), tokens=(),
        hero_task="完成调制猫粮检定，推进说服进度",
        traitor_task="以检定让恶猫捣乱，拖延调制",
        hero_stat=("sanity", "knowledge"), hero_target=5,
        required_cards=(),
        trigger_hint="官方触发：餐厅/厨房/仆人房/剧院 × 猫（官方 #60，怪物 The Cat/Kittens）",
        engine_note="官方预兆 Cat 未落位（P 表预兆位 +5 限额）；Kittens 未生成。",
    ),
    81: dict(
        mode="ww_haunt_81", traitor_rule="revealer",
        hero_goal="摧毁藏宝箱：累计 4 枚力量检定标记后下一次命中即毁。",
        traitor_goal="化身海盗船长 Captain Sting，率船员夺走宝藏并杀光英雄。",
        rooms=("catacombs", "dungeon", "furnace_room", "pentagram_chamber"), tokens=(),
        hero_task="完成破箱检定，推进摧毁进度",
        traitor_task="以力量检定守护宝箱",
        hero_stat=("might",), hero_target=4,
        required_cards=("omen_box",),
        trigger_hint="官方触发：地下墓穴/地牢/熔炉房/五芒星室 × 盒子（官方 #61，怪物 Captain Sting/Pirates/Treasure Chest）",
        engine_note="藏宝箱简化为英雄进度轨（4 枚标记后轨满即胜）。",
    ),
    82: dict(
        mode="ww_haunt_82", traitor_rule="revealer",
        hero_goal="按顺序完成五幕演出并让哈姆雷特（叛徒）活到剧终。",
        traitor_goal="扮演哈姆雷特王子：若在剧终前死亡，英雄失败。",
        rooms=("theater",), tokens=(),
        hero_task="完成台词检定，推进演出进度",
        traitor_task="以检定即兴发挥，打乱剧本顺序",
        hero_stat=("knowledge", "sanity"), hero_target=5,
        required_cards=("omen_mask",),
        trigger_hint="官方触发：剧院 × 血岩/面具/头骨/长矛/小瓶（官方 #62）",
        engine_note="五幕折算为英雄进度轨；'让叛徒活到剧终'由通用兜底覆盖（叛徒死=英雄胜的官方特例记为简化）。",
    ),
    83: dict(
        mode="ww_haunt_83", traitor_rule="revealer",
        hero_goal="收集正确的魔法书夺回声音，并杀死面具怪人。",
        traitor_goal="看守魔法盒 Voicebox 的面具怪人：夺取所有人的声音。",
        rooms=("abandoned_room", "balcony", "charred_room", "theater"), tokens=(),
        hero_task="完成检索检定，找回正确的魔法书",
        traitor_task="以理智检定吞噬声音",
        hero_stat=("knowledge",), hero_target=5,
        required_cards=("omen_box", "omen_book"),
        trigger_hint="官方触发：废弃房间/阳台/烧焦的房间/剧院 × 盒子（官方 #63）",
        engine_note="真人禁言规则为桌上规则，不进引擎。",
    ),
    84: dict(
        mode="ww_haunt_84", traitor_rule="lowest_knowledge",
        hero_goal="任一英雄从门厅前门走出房屋（防御靠通灵板拼字）。",
        traitor_goal="其余探索者皆成骚灵：把最后的英雄变成常驻怨灵。",
        rooms=("dungeon", "rookery", "study", "theater"), tokens=(),
        hero_task="完成拼字检定，推进开门进度",
        traitor_task="以检定强化怨灵封印",
        hero_stat=("knowledge", "sanity"), hero_target=5,
        required_cards=("omen_spirit_board",),
        trigger_hint="官方触发：地牢/鸦舍/书房/剧院 × 通灵板（官方 #64，多叛徒 Poltergeist）",
        engine_note="官方多叛徒降级为'知识最低者'形式叛徒。",
    ),
    85: dict(
        mode="ww_haunt_85", traitor_rule="revealer",
        hero_goal="在房屋被淹完之前杀死变身鱼人的朋友。",
        traitor_goal="鱼人 Merperson：让房屋彻底淹没。",
        rooms=("dungeon", "nursery", "rookery", "study"), tokens=(),
        hero_task="完成猎杀检定，推进击杀进度",
        traitor_task="以检定抬升水位",
        hero_stat=("might",), hero_target=5,
        required_cards=("omen_spear",),
        trigger_hint="官方触发：地牢/育儿室/鸦舍/书房 × 长矛（官方 #65）",
        engine_note="水位上升折算为叛徒进度轨。",
    ),
    86: dict(
        mode="ww_haunt_86", traitor_rule="revealer",
        hero_goal="英雄合计夺取 4 位选举人，或杀死枢机主教 Sinn。",
        traitor_goal="枢机主教：带 4 张选举人票上屋顶当选教皇，并血洗房屋。",
        rooms=("dungeon", "nursery", "rookery", "theater"), tokens=(),
        hero_task="完成夺取检定，累计选举人票",
        traitor_task="以检定护送选举人上屋顶",
        hero_stat=("might", "speed"), hero_target=4,
        required_cards=("omen_holy_symbol",),
        trigger_hint="官方触发：地牢/育儿室/鸦舍/剧院 × 圣徽（官方 #86，怪物 Elector ×7）",
        engine_note="7 枚 Elector 令牌折算为双进度轨；'上屋顶'以触发房映射关键房间。",
    ),
    87: dict(
        mode="ww_haunt_87", traitor_rule="highest_speed",
        hero_goal="在育儿室集齐知识/理智标记，把恶灵诱出血岩。",
        traitor_goal="被恶霸男孩之灵附身：用致命投石游戏杀死所有英雄。",
        rooms=("balcony", "dining_room", "kitchen", "nursery"), tokens=(),
        hero_task="完成诱捕检定，推进诱出进度",
        traitor_task="以速度检定投掷致命石球",
        hero_stat=("sanity", "knowledge"), hero_target=5,
        required_cards=("omen_bloodstone",),
        trigger_hint="官方触发：阳台/餐厅/厨房/育儿室 × 血岩（官方 #87，怪物 Bully 恶灵）",
        engine_note="Bully 恶灵藏于血岩的设定折算为双进度轨。",
    ),
    88: dict(
        mode="ww_haunt_88", traitor_rule="highest_knowledge",
        hero_goal="找出并摧毁死灵法师 Maldovo 的魂器（Soulcrux）。",
        traitor_goal="藏起灵魂的死灵法师：杀死所有英雄。",
        rooms=("junk_room", "nursery", "servants_quarters", "theater"), tokens=(),
        hero_task="完成探魂检定，摧毁魂器",
        traitor_task="以知识检定藏匿灵魂",
        hero_stat=("knowledge",), hero_target=5,
        required_cards=("omen_key",),
        trigger_hint="官方触发：杂物间/育儿室/仆人房/剧院 × 钥匙（官方 #68，怪物 Wraith）",
        engine_note="鸭-兔-蛋嵌套藏匿简化为英雄进度轨。",
    ),
    89: dict(
        mode="ww_haunt_89", traitor_rule="revealer",
        hero_goal="让所有存活英雄免于绞刑架（撑过老西部刽子手的限时猎杀）。",
        traitor_goal="被老西部刽子手之灵附身：把英雄一个个送上绞刑架。",
        rooms=("catacombs", "charred_room", "cave"), tokens=(),
        hero_task="完成挣脱检定，从绞索中救下同伴",
        traitor_task="以力量检定收紧绞索",
        hero_stat=("speed", "might"), hero_target=5,
        required_cards=(),
        trigger_hint="官方触发：地下墓穴/烧焦的房间/洞穴 × 绳（官方 #69；预兆 Rope 未落位）",
        engine_note="官方预兆 Rope 未落位（P 表预兆位 +5 限额）。",
    ),
    90: dict(
        mode="ww_haunt_90", traitor_rule="revealer",
        hero_goal="夺走叛徒的全部思想（Thought），在失去所有思想前揭穿它。",
        traitor_goal="变成 Brainstraws 吸食思想的怪物：吸光所有英雄的思想。",
        rooms=("balcony", "gallery", "rookery", "study"), tokens=(),
        hero_task="完成夺回检定，抢回思想",
        traitor_task="以理智检定吸取思想",
        hero_stat=("sanity", "knowledge"), hero_target=5,
        required_cards=("omen_vial",),
        trigger_hint="官方触发：阳台/画廊/鸦舍/书房 × 小瓶（官方 #70）",
        engine_note="Thought 令牌折算为双进度轨。",
    ),
    91: dict(
        mode="ww_haunt_91", traitor_rule="left_of_revealer",
        hero_goal="杀死叛徒，让他加入你们的死后世界（英雄是鬼魂，回合结束未攻击 +1 理智）。",
        traitor_goal="企图把鬼魂们赶走的人：把所有英雄逐出阴宅。",
        rooms=("balcony", "gallery", "junk_room", "servants_quarters"), tokens=(),
        hero_task="完成超度检定，送叛徒入死后世界",
        traitor_task="以检定净化阴宅，驱逐鬼魂",
        hero_stat=("sanity", "might"), hero_target=5,
        required_cards=(),
        trigger_hint="官方触发：阳台/画廊/杂物间/仆人房 × 绳（官方 #71，英雄为 Ghost；预兆 Rope 未落位）",
        engine_note="英雄 Ghost 属性修正未实现（回合结束 +1 理智为官方规则）。",
    ),
    92: dict(
        mode="ww_haunt_92", traitor_rule="revealer",
        hero_goal="杀死与地狱犬融合的朋友——The Beast。",
        traitor_goal="The Beast（外表是可爱小狗）：咬死所有英雄。",
        rooms=("dungeon", "nursery", "study", "theater"), tokens=(),
        hero_task="完成猎杀检定，推进击杀进度",
        traitor_task="以力量检定撕咬英雄",
        hero_stat=("might",), hero_target=5,
        required_cards=("omen_dog",),
        trigger_hint="官方触发：地牢/育儿室/书房/剧院 × 狗（官方 #72，怪物 The Beast）",
        engine_note="The Beast 怪物未生成，以叛徒检定轨道近似。",
    ),
    93: dict(
        mode="ww_haunt_93", traitor_rule="revealer",
        hero_goal="连续多回合拥抱叛徒使其复原，再一起拥抱小礼貌脑袋 The Head。",
        traitor_goal="带着新朋友 The Head 想喂食英雄。",
        rooms=("dungeon", "nursery", "rookery", "study"), tokens=(),
        hero_task="完成拥抱检定，推进安抚进度",
        traitor_task="以检定喂食 The Head",
        hero_stat=("sanity",), hero_target=5,
        required_cards=("omen_skull",),
        trigger_hint="官方触发：地牢/育儿室/鸦舍/书房 × 头骨（官方 #73，怪物 The Head）",
        engine_note="'杀死叛徒也算英雄胜'的官方备选线由通用兜底覆盖。",
    ),
    94: dict(
        mode="ww_haunt_94", traitor_rule="revealer",
        hero_goal="杀死小丑 Knick-Knack，或摧毁其全部 Gags 笑话陷阱（2 名英雄被杀则失败）。",
        traitor_goal="小丑 Knick-Knack：用 Gag 笑话陷阱杀人，还有恶犬 Noodles 助拳。",
        rooms=("nursery",), tokens=(),
        hero_task="完成拆解检定，摧毁笑话陷阱",
        traitor_task="以检定布置 Gag 陷阱",
        hero_stat=("knowledge", "might"), hero_target=5,
        required_cards=("omen_madman",),
        trigger_hint="官方触发：育儿室 × 咬伤/猫/疯子/面具（官方 #74，怪物 Noodles the Dog）",
        engine_note="Gag 陷阱折算为双进度轨；Noodles 未生成。",
    ),
    95: dict(
        mode="ww_haunt_95", traitor_rule="left_of_revealer",
        hero_goal="杀死冰雪女王，或锁上 6 个恒温器并把回合轨降到 0。",
        traitor_goal="被童年记忆触发变成的冰雪女王：冰封全屋，冻死所有英雄。",
        rooms=("furnace_room",), tokens=(),
        hero_task="完成封炉检定，推进解锁恒温器进度",
        traitor_task="以检定加速冰封",
        hero_stat=("might", "knowledge"), hero_target=5,
        required_cards=("omen_key",),
        trigger_hint="官方触发：熔炉房 × 猫/钥匙/照片/绳（官方 #75，怪物 Snow Monster；mega 前置）",
        engine_note="Thermostat/回合轨折算为双进度轨。",
    ),
    96: dict(
        mode="ww_haunt_96", traitor_rule="revealer",
        hero_goal="在回合轨到 0 之前揭发来自过去/未来的前作探索者。",
        traitor_goal="完成导致英雄被谋杀的仪式。",
        rooms=("gallery", "junk_room", "master_bedroom", "study"), tokens=(),
        hero_task="完成取证检定，揭发叛徒的谋杀仪式",
        traitor_task="以检定推进谋杀仪式",
        hero_stat=("knowledge",), hero_target=5,
        required_cards=("omen_photograph",),
        trigger_hint="官方触发：画廊/杂物间/主卧/书房 × 照片（官方 #76）",
        engine_note="Turn/Damage 轨倒计时折算为双方竞速轨道。",
    ),
    97: dict(
        mode="ww_haunt_97", traitor_rule="revealer",
        hero_goal="找到彩虹尽头的金罐（Pot of Gold）。",
        traitor_goal="爱尔兰矮妖 Leprechaun：在英雄找到金罐前杀光他们。",
        rooms=("dungeon", "rookery", "study", "theater"), tokens=(),
        hero_task="完成寻金检定，推进寻找进度",
        traitor_task="以检定把彩虹挪走",
        hero_stat=("knowledge", "speed"), hero_target=5,
        required_cards=("omen_medallion",),
        trigger_hint="官方触发：地牢/鸦舍/书房/剧院 × 徽章（官方 #77）",
        engine_note="Pot of Gold 令牌折算为英雄进度轨。",
    ),
    98: dict(
        mode="ww_haunt_98", traitor_rule="lowest_sanity_except_revealer",
        hero_goal="说出 The Fiend 的真名将其放逐。",
        traitor_goal="被古老实体附身：以亵渎之名吞噬所有身份。",
        rooms=("study",), tokens=(),
        hero_task="完成真名检定，放逐 The Fiend",
        traitor_task="以检定吞噬身份",
        hero_stat=("knowledge", "sanity"), hero_target=5,
        required_cards=("omen_book",),
        trigger_hint="官方触发：书房 × 书/猫/圣徽/信/面具（官方 #78，怪物 The Fiend=叛徒）",
        engine_note="官方预兆 Cat/Letter 未落位（P 表预兆位 +5 限额）。",
    ),
    99: dict(
        mode="ww_haunt_99", traitor_rule="revealer",
        hero_goal="杀死能量双体双子之一。",
        traitor_goal="两位叛徒合成能量双体：布设 Nodes 把房屋撕成碎片。",
        rooms=("charred_room", "gallery", "gymnasium", "junk_room"), tokens=(),
        hero_task="完成破核检定，瓦解双子",
        traitor_task="以检定布设撕裂节点",
        hero_stat=("might",), hero_target=5,
        required_cards=("omen_bloodstone",),
        trigger_hint="官方触发：烧焦的房间/画廊/健身房/杂物间 × 血岩（官方 #79，双叛徒）",
        engine_note="官方双叛徒按单叛徒模型降级；Nodes 折算为叛徒进度轨。",
    ),
    100: dict(
        mode="ww_haunt_100", traitor_rule="highest_knowledge",
        hero_goal="把回合轨降到 0，摧毁研究实验室。",
        traitor_goal="半疯狂的科学家：用电网 Electronet 捕捉猴子完成实验。",
        rooms=("dungeon", "kitchen", "nursery", "servants_quarters"), tokens=(),
        hero_task="完成拆除检定，捣毁研究实验室",
        traitor_task="以知识检定扩建电网",
        hero_stat=("knowledge", "might"), hero_target=5,
        required_cards=("omen_vial",),
        trigger_hint="官方触发：地牢/厨房/育儿室/仆人房 × 小瓶（官方 #80，怪物 Monkey ×7）",
        engine_note="Monkey 怪物未生成；Turn/Damage 轨折算为双进度轨。",
    ),
    101: dict(
        mode="ww_haunt_101", traitor_rule="revealer",
        hero_goal="识破法老的诅咒，把正确的卡诺卜罐带回门厅。",
        traitor_goal="在五芒星室开启棺罐唤醒木乃伊的人：让英雄困死在诅咒里。",
        rooms=("pentagram_chamber",), tokens=(),
        hero_task="完成识罐检定，把正确的罐子带回门厅",
        traitor_task="以检定强化诅咒",
        hero_stat=("knowledge",), hero_target=5,
        required_cards=("omen_key",),
        trigger_hint="官方触发：五芒星室 × 猫/钥匙/绳/小瓶（官方 #81，怪物 Mummy）",
        engine_note="官方预兆 Cat/Rope 未落位；Jar 令牌折算为英雄进度轨。",
    ),
    102: dict(
        mode="ww_haunt_102", traitor_rule="revealer",
        hero_goal="警察抵达前，每名英雄都建立不在场证明。",
        traitor_goal="勒死屋主的管家 Butler：布置不在场证明悬案，逐个绞死英雄。",
        rooms=("dining_room", "kitchen", "master_bedroom", "study"), tokens=(),
        hero_task="完成取证检定，建立不在场证明",
        traitor_task="以检定布置伪证",
        hero_stat=("knowledge",), hero_target=5,
        required_cards=(),
        trigger_hint="官方触发：餐厅/厨房/主卧/书房 × 绳（官方 #82；预兆 Rope 未落位）",
        engine_note="Rope 条件（不在场证明其一需用绳且绳不在餐厅）为桌上规则。",
    ),
    103: dict(
        mode="ww_haunt_103", traitor_rule="revealer",
        hero_goal="成为屋内最后一人，或找到契约（Contract）的漏洞。",
        traitor_goal="无常规叛徒：全员互杀以免被地狱献祭（形式叛徒驱动献祭倒计时）。",
        rooms=("catacombs", "charred_room", "furnace_room", "pentagram_chamber"), tokens=(),
        hero_task="完成翻约检定，找出契约漏洞",
        traitor_task="以检定收紧契约条款",
        hero_stat=("knowledge", "sanity"), hero_target=5,
        required_cards=(),
        trigger_hint="官方触发：地下墓穴/烧焦的房间/熔炉房/五芒星室 × 信（官方 #83；核心卡为事件 Contract，已落位）",
        engine_note="官方预兆 Letter 未落位；Contract 事件卡已在 content.py 新事件集。",
    ),
    104: dict(
        mode="ww_haunt_104", traitor_rule="left_of_revealer",
        hero_goal="杀死附身每一具躯体的心灵凶手 Richard Smith，或让叛徒自愿抹除其记忆。",
        traitor_goal="被心灵感应凶手的记忆小屋支配：让凶手人格占据所有英雄。",
        rooms=("dungeon", "nursery", "study", "theater"), tokens=(),
        hero_task="完成驱灵检定，夺回躯体",
        traitor_task="以检定扩散附身",
        hero_stat=("sanity", "knowledge"), hero_target=5,
        required_cards=("omen_crystal_ball",),
        trigger_hint="官方触发：地牢/育儿室/书房/剧院 × 水晶球（官方 #84）",
        engine_note="附身机制折算为双进度轨；'叛徒可倒戈'为桌上规则。",
    ),
    105: dict(
        mode="ww_haunt_105", traitor_rule="left_of_revealer",
        hero_goal="至少一名理智为正的英雄逃出房屋（可呼叫警察支援）。",
        traitor_goal="被某种存在逼疯者：让狂气传染所有人。",
        rooms=("dungeon", "nursery", "rookery", "study"), tokens=(),
        hero_task="完成求援检定，从门厅逃出",
        traitor_task="以检定传播狂气",
        hero_stat=("speed", "sanity"), hero_target=5,
        required_cards=("omen_ring",),
        trigger_hint="官方触发：地牢/育儿室/鸦舍/书房 × 戒指（官方 #85）",
        engine_note="Smartphone/信号/Dead Zone 机制折算为双进度轨。",
    ),
    106: dict(
        mode="ww_haunt_106", traitor_rule="revealer",
        hero_goal="砍倒叛徒变成的巨树 The Tree。",
        traitor_goal="巨大且迅速生长的巨树：吞没整座房屋。",
        rooms=("abandoned_room", "gymnasium", "nursery", "rookery"), tokens=(),
        hero_task="完成砍伐检定，削减巨树",
        traitor_task="以检定加速生长",
        hero_stat=("might",), hero_target=5,
        required_cards=(),
        trigger_hint="官方触发：废弃房间/健身房/育儿室/鸦舍 × 绳（官方 #86，怪物 Squirrels；mega 前置）",
        engine_note="Squirrels 未生成；Rope 未落位。",
    ),
    107: dict(
        mode="ww_haunt_107", traitor_rule="revealer",
        hero_goal="找到女校长之灵，完成对恶灵 Siblings 的驱魔。",
        traitor_goal="被屋内 Siblings 恶灵附身：恶作剧致死，杀光英雄。",
        rooms=("balcony", "kitchen", "nursery", "rookery"), tokens=(),
        hero_task="完成驱魔检定，推进净化进度",
        traitor_task="以检定恶作剧害人",
        hero_stat=("sanity", "knowledge"), hero_target=5,
        required_cards=("omen_book",),
        trigger_hint="官方触发：阳台/厨房/育儿室/鸦舍 × 信（官方 #87，怪物 Sibling 恶灵）",
        engine_note="官方预兆 Letter 未落位。",
    ),
    108: dict(
        mode="ww_haunt_108", traitor_rule="revealer",
        hero_goal="杀死行走的神——叛徒化身巴比伦神 Marduk。",
        traitor_goal="Nebuchadnezzar 化身：吞魂夺力，重建巴比伦。",
        rooms=("abandoned_room", "balcony", "catacombs", "gallery", "junk_room"), tokens=(),
        hero_task="完成讨伐检定，削弱神躯",
        traitor_task="以检定吞魂夺力",
        hero_stat=("might", "sanity"), hero_target=5,
        required_cards=("omen_mask",),
        trigger_hint="官方触发：废弃房间/阳台/地下墓穴/画廊/杂物间 × 猫（官方 #88，怪物 Lammasu）",
        engine_note="Lammasu 守卫未生成；Cat 未落位。",
    ),
    109: dict(
        mode="ww_haunt_109", traitor_rule="lowest_sanity",
        hero_goal="全部存活英雄从（上锁的）前门逃出（可演戏开锁 Stage a Farce）。",
        traitor_goal="雨夜留宿的怪医生 The Doctor：用前任住客的尸体拼缝怪物杀死英雄。",
        rooms=("balcony", "dining_room", "dungeon", "kitchen"), tokens=(),
        hero_task="完成开锁检定，从前门逃出",
        traitor_task="以检定缝合怪物",
        hero_stat=("speed", "knowledge"), hero_target=5,
        required_cards=("omen_photograph",),
        trigger_hint="官方触发：阳台/餐厅/地牢/厨房 × 照片（官方 #89）",
        engine_note="前门上锁与演戏开锁为桌上规则；拼缝怪物未生成。",
    ),
    110: dict(
        mode="ww_haunt_110", traitor_rule="revealer",
        hero_goal="成为最后活着的实习生。",
        traitor_goal="爱摆架子的员工体系：让实习生全部出局（没咖啡就发飙）。",
        rooms=("balcony", "dining_room", "master_bedroom", "study"), tokens=(),
        hero_task="完成摸鱼检定，躲过员工刁难",
        traitor_task="以检定刁难实习生",
        hero_stat=("speed", "knowledge"), hero_target=5,
        required_cards=("omen_key",),
        trigger_hint="官方触发：阳台/餐厅/主卧/书房 × 钥匙（官方 #90）",
        engine_note="Employee 模型未生成。",
    ),
    111: dict(
        mode="ww_haunt_111", traitor_rule="lowest_sanity",
        hero_goal="烧掉房内每一个房间（Fire token，以火净宅）。",
        traitor_goal="与蔓延的黑暗 The Darkness 同化：吞噬所有光。",
        rooms=("catacombs", "dining_room", "furnace_room", "junk_room"), tokens=(),
        hero_task="完成纵火检定，以火净宅",
        traitor_task="以检定扑灭火焰、扩散黑暗",
        hero_stat=("might",), hero_target=5,
        required_cards=("omen_vial",),
        trigger_hint="官方触发：地下墓穴/餐厅/熔炉房/杂物间 × 小瓶（官方 #91）",
        engine_note="Fire token 折算为英雄进度轨。",
    ),
    112: dict(
        mode="ww_haunt_112", traitor_rule="revealer",
        hero_goal="发现并放置最后一块房间板块（放置者胜；无法再放则最后放置者胜）。",
        traitor_goal="无常规叛徒：全员与幽灵竞速探索（形式叛徒驱动竞速检定）。",
        rooms=("gymnasium",), tokens=(),
        hero_task="完成竞速探索检定，抢下最后一块板块",
        traitor_task="以速度检定拖慢竞速",
        hero_stat=("speed",), hero_target=5,
        required_cards=("omen_key",),
        trigger_hint="官方触发：健身房 × 猫/钥匙/照片/小瓶（官方 #92，Ghost token）",
        engine_note="幽灵竞速折算为双进度轨；官方预兆 Cat 未落位。",
    ),
    113: dict(
        mode="ww_haunt_113", traitor_rule="highest_knowledge",
        hero_goal="把乐于当猫头鹰的叛徒变回人类。",
        traitor_goal="整座房屋滑向悬崖：让英雄随屋坠落。",
        rooms=("rookery",), tokens=(),
        hero_task="完成变形检定，把叛徒变回人类",
        traitor_task="以检定让房屋滑向悬崖",
        hero_stat=("knowledge", "sanity"), hero_target=5,
        required_cards=("omen_bloodstone", "omen_key"),
        trigger_hint="官方触发：鸦舍 × 血岩/书/水晶球/钥匙（官方 #93；mega 前置）",
        engine_note="悬崖滑移折算为叛徒进度轨。",
    ),
    114: dict(
        mode="ww_haunt_114", traitor_rule="revealer",
        hero_goal="把贪婪姑婆 Edwina 的灵魂封进她收藏的传家宝。",
        traitor_goal="被姑婆之灵附身：收回全部收藏传家宝（可偷/交易物品）。",
        rooms=("catacombs", "pentagram_chamber", "rookery", "servants_quarters"), tokens=(),
        hero_task="完成封灵检定，封印姑婆",
        traitor_task="以检定回收传家宝",
        hero_stat=("knowledge",), hero_target=5,
        required_cards=("omen_photograph", "omen_ring"),
        trigger_hint="官方触发：地下墓穴/五芒星室/鸦舍/仆人房 × 照片（官方 #94）",
        engine_note="Bequest 传家宝折算为双进度轨。",
    ),
    115: dict(
        mode="ww_haunt_115", traitor_rule="revealer",
        hero_goal="全员逃到（上锁的）前门外。",
        traitor_goal="有魔法、严格秩序的保姆 The Nanny：把顽童们变回婴儿关进育儿室。",
        rooms=("nursery",), tokens=(),
        hero_task="完成开锁检定，从前门逃出",
        traitor_task="以检定施展婴儿魔法",
        hero_stat=("speed", "knowledge"), hero_target=5,
        required_cards=("omen_book", "omen_medallion"),
        trigger_hint="官方触发：育儿室 × 书/徽章/照片/通灵板（官方 #95）",
        engine_note="前门上锁为桌上规则。",
    ),
    116: dict(
        mode="ww_haunt_116", traitor_rule="left_of_revealer",
        hero_goal="任一英雄在自己回合结束时与所有存活英雄同处废弃房间。",
        traitor_goal="阻止所有人逃离者：召唤幽灵牛头怪（真假难辨）。",
        rooms=("abandoned_room",), tokens=(),
        hero_task="完成集合检定，让全员聚齐废弃房间",
        traitor_task="以检定驱散集合",
        hero_stat=("speed", "sanity"), hero_target=5,
        required_cards=("omen_bloodstone", "omen_key", "omen_photograph", "omen_vial"),
        trigger_hint="官方触发：废弃房间 × 血岩/钥匙/照片/小瓶（官方 #96，怪物 Minotaur 或幻象）",
        engine_note="集合聚齐条件折算为英雄进度轨；牛头怪未生成。",
    ),
    117: dict(
        mode="ww_haunt_117", traitor_rule="revealer",
        hero_goal="杀死隐藏的狼孩叛徒；每次有探索者死亡即翻开其 Origin，若为 1 号则英雄胜。",
        traitor_goal="狼孩（其本人也不知情）：建造有破坏暗门的 Barricade 并隐藏 Origin。",
        rooms=("dungeon", "rookery", "study", "theater"), tokens=(),
        hero_task="完成猎狼检定，找出狼孩",
        traitor_task="以检定建造路障",
        hero_stat=("might", "knowledge"), hero_target=5,
        required_cards=("omen_bite",),
        trigger_hint="官方触发：地牢/鸦舍/书房/剧院 × 咬伤（官方 #97，隐藏叛徒）",
        engine_note="隐藏叛徒机制降级为普通叛徒；Origin 翻牌规则为桌上规则。",
    ),
    118: dict(
        mode="ww_haunt_118", traitor_rule="revealer",
        hero_goal="所有人体模型离开房屋，且至少一名英雄存活。",
        traitor_goal="意识被人体模型集体吸收的朋友（本剧本叛徒与英雄胜负一致）。",
        rooms=("master_bedroom",), tokens=(),
        hero_task="完成唤醒检定，护送人体模型离开",
        traitor_task="以检定唤醒更多人偶",
        hero_stat=("sanity", "speed"), hero_target=5,
        required_cards=("omen_bloodstone", "omen_box", "omen_vial"),
        trigger_hint="官方触发：主卧 × 血岩/盒子/猫/小瓶（官方 #98，怪物 Mannequin 群）",
        engine_note="官方预兆 Cat 未落位；'胜负一致'的 meta 剧本按通用胜负判定。",
    ),
    119: dict(
        mode="ww_haunt_119", traitor_rule="revealer",
        hero_goal="在重开的新局中抽到盒子（Box）预兆（计时结束未找到则失败）。",
        traitor_goal="无叛徒的 meta 剧本：本剧本是重新开一局 Betrayal 的元宇宙剧本（形式叛徒驱动计时）。",
        rooms=("dining_room", "kitchen", "nursery", "study"), tokens=(),
        hero_task="完成翻箱倒柜检定，找到盒子",
        traitor_task="以检定收走线索",
        hero_stat=("knowledge", "speed"), hero_target=5,
        required_cards=("omen_box",),
        trigger_hint="官方触发：餐厅/厨房/育儿室/书房 × 盒子（官方 #99，无叛徒 meta 剧本）",
        engine_note="重开新局为桌上规则；引擎折算为找盒子的进度轨竞速。",
    ),
    120: dict(
        mode="ww_haunt_120", traitor_rule="revealer",
        hero_goal="在死亡或回合轨到 0 之前完成自己的全部挑战。",
        traitor_goal="无叛徒：Hangman 猜词死亡游戏（形式叛徒驱动倒计时）。",
        rooms=("abandoned_room", "dungeon", "gymnasium", "junk_room"), tokens=(),
        hero_task="完成猜词检定，推进个人挑战",
        traitor_task="以检定收紧倒计时",
        hero_stat=("knowledge",), hero_target=5,
        required_cards=("omen_book",),
        trigger_hint="官方触发：废弃房间/地牢/健身房/杂物间 × 信（官方 #100，无叛徒）",
        engine_note="每人专属 Challenges 折算为英雄进度轨。",
    ),
}


WW_HAUNT_RULES: dict[int, dict[str, Any]] = {
    haunt_id: _make_scenario_rule(
        haunt_id,
        mode=str(definition["mode"]),
        traitor_rule=str(definition["traitor_rule"]),
        hero_goal=str(definition["hero_goal"]),
        traitor_goal=str(definition["traitor_goal"]),
        rooms=tuple(definition["rooms"]),
        monsters=(),
        tokens=tuple(definition["tokens"]),
        hero_task=str(definition["hero_task"]),
        traitor_task=str(definition["traitor_task"]),
        hero_stat=definition.get("hero_stat", "knowledge"),
        hero_target=int(definition.get("hero_target", 5)),
        required_cards=tuple(definition.get("required_cards", ())),
        engine_note=str(definition.get("engine_note", "")),
    )
    for haunt_id, definition in WW_SCENARIO_TABLE.items()
}


# ----------------------------------------------------------------------
# 激活（本轮不调用）
# ----------------------------------------------------------------------
def activate() -> dict:
    """把 WW 集合挂回 content 模块；返回各项追加计数。幂等。"""
    try:
        from . import content as _content
    except ImportError:
        import content as _content  # type: ignore

    added = {
        "FLOOR_ROOF": 1,
        "ROOF_ROOMS": 0,
        "WW_EVENT_ADDITIONS": 0,
        "WW_ITEM_ADDITIONS": 0,
        "WW_OMEN_ADDITIONS": 0,
        "WW_HAUNT_NAMES": 0,
        "WW_MONSTER_ADDITIONS": 0,
    }
    _content.FLOOR_ROOF = FLOOR_ROOF
    if not hasattr(_content, "ROOF_ROOMS"):
        _content.ROOF_ROOMS = ROOF_ROOMS
        added["ROOF_ROOMS"] = len(ROOF_ROOMS)
    if not hasattr(_content, "ROOF_ROOM_IDS"):
        _content.ROOF_ROOM_IDS = ROOF_ROOM_IDS

    for attr, payload in (
        ("OMEN_CARDS", WW_OMEN_ADDITIONS),
        ("ITEM_CARDS", WW_ITEM_ADDITIONS),
        ("MONSTER_BASES", WW_MONSTER_ADDITIONS),
    ):
        bucket = getattr(_content, attr)
        existing = {item["id"] for item in bucket}
        for item in payload:
            if item["id"] not in existing:
                bucket.append(item)
                added["WW_%s" % attr.split("_")[0] + "_ADDITIONS"] += 1

    specs = _content.EVENT_SUPPLEMENTAL_SPECS
    have = {spec[0] for spec in specs}
    for spec in WW_EVENT_ADDITIONS:
        if spec[0] not in have:
            specs.append(spec)
            added["WW_EVENT_ADDITIONS"] += 1

    names = _content.HAUNT_NAMES
    have_ids = {row[0] for row in names}
    for row in WW_HAUNT_NAMES:
        if row[0] not in have_ids:
            names.append(row)
            added["WW_HAUNT_NAMES"] += 1
    return added
