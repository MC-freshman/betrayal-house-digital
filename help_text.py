"""面向玩家的规则 / 卡牌 / 房间说明生成（悬停提示、详情弹窗、帮助面板共用）。

- card_usage(card)      返回某张卡牌"怎么用、什么时候用"的详细说明。
- card_short(card)      返回一句话短说明（适合列表里显示）。
- room_effect_detail()  返回房间特殊效果的一句话说明（比引擎里的更全）。
- rules_text()          基本规则速查（帮助面板用）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from models import Card


# 属性中文名
STAT_CN = {"speed": "速度", "might": "力量", "sanity": "理智", "knowledge": "知识"}
STAT_ORDER = ("speed", "might", "sanity", "knowledge")


def card_usage(card) -> str:
    """返回卡牌的详细用法说明；没有规则说明时返回空字符串。"""
    eid = card.effect_id
    bonus = card.bonus or {}
    data = card.data or {}
    attack = int(bonus.get("attack", 0))
    heal = int(data.get("heal", 1))
    kind = data.get("kind", "")

    # ------------------------------------------------------------ 武器
    if eid == "item_weapon":
        return f"攻击武器：作祟阶段攻击时选择使用，攻击骰 +{attack}。"
    if eid == "item_weapon_blood":
        return f"血武器：攻击骰 +{attack}，但每次使用自身受 1 点物理伤害。"
    if eid == "item_dynamite":
        return f"炸药（一次性）：攻击骰 +{attack}，使用后销毁。"
    if eid == "item_revolver":
        return f"远程武器：攻击骰 +{attack}；可攻击同一直线（视线内）目标，被反击时不受伤。"
    if eid == "item_weapon_sacrifice":
        return f"献祭武器：攻击骰 +{attack}，但每次使用自身受 1 点物理伤害。"

    # ------------------------------------------------------------ 治疗
    if eid in ("item_heal_small", "item_heal_large"):
        stats = "速度/力量" if kind == "physical" else "理智/知识"
        return f"治疗（一次性）：使用后为「{stats}」之一恢复 {heal} 点。"
    if eid == "item_heal_sanity":
        return f"治疗（一次性）：使用后为「理智/知识」之一恢复 {heal} 点。"

    # ------------------------------------------------------------ 其它物品
    if eid == "item_adrenaline":
        return f"使用（一次性）：本回合移动步数 +{int(data.get('speed_bonus', 3))}。"
    if eid == "item_angel_feather":
        return "使用（一次性）：下一次检定自动成功。"
    if eid == "item_armor":
        return "被动：受到物理伤害时可用它挡下一次（挡下后销毁）。"
    if eid == "item_music_box":
        return f"使用（一次性）：让同房间一只怪物昏迷 {int(data.get('stun', 2))} 回合。"
    if eid == "item_bottle":
        return f"使用（一次性）：随机使一项属性 ±{int(data.get('random_shift', 1))}。"
    if eid == "item_dark_dice":
        return f"使用：随机使一项属性 ±{int(data.get('random_shift', 1))}（可重复使用）。"
    if eid == "item_amulet":
        return f"使用（一次性）：指定一项属性 +{int(data.get('stat_boost', 1))}。"
    if eid == "item_pickpocket":
        return "使用（一次性）：从同房间一名玩家身上偷 1 件物品。"
    if eid == "item_puzzle_box":
        return f"使用（一次性）：打开获得 {int(data.get('draw_items', 2))} 张物品卡。"
    if eid == "item_reroll":
        return "被动：检定失败时可多一次重掷。"

    # ------------------------------------------------------------ 预兆
    if eid == "omen_book":
        return "预兆：检定「知识」时 +2。"
    if eid == "omen_crystal_ball":
        return "预兆：检定「知识」时 +2，且失败可多一次重掷。"
    if eid == "omen_holy_symbol":
        return "预兆：检定「理智」时 +2。"
    if eid == "omen_mask":
        return "预兆：攻击时攻击骰 +1。"
    if eid == "omen_medallion":
        return "预兆：检定「理智」时 +1。"
    if eid == "omen_ring":
        return "预兆：检定「知识」时 +1。"
    if eid == "omen_spear":
        return "预兆·武器：攻击时攻击骰 +2。"
    if eid == "omen_spirit_board":
        return "预兆：检定「知识」时 +2。"
    if eid == "omen_bite":
        return "预兆·诅咒：作祟触发器，可能带来厄运。"
    if eid == "omen_skull":
        return "预兆·钥匙：作祟触发器。"
    if eid == "omen_companion":
        return "预兆·同伴：不可交易/偷取，会一直跟随你。"

    # ------------------------------------------------------------ 事件
    if eid == "event_bloody_vision":
        return "触发：理智检定（目标 4）失败受 1 点物理伤害。"
    if eid == "event_grave_dirt":
        return "触发：受 1 点物理伤害。"
    if eid == "event_lights_out":
        return "触发：本回合移动步数降为最多 1。"
    if eid in ("event_mists_from_the_walls", "event_silence"):
        return "触发：所有在地下室的玩家受 1 点精神伤害。"
    if eid == "event_mystic_slide":
        return "触发：被送到地下室平台。"
    if eid == "event_secret_passage":
        return "触发：在当前楼层生成一条秘密通道。"
    if eid == "event_secret_stairs":
        return "触发：生成一条跨楼层秘密楼梯。"
    if eid in ("event_lost_one", "event_the_walls"):
        return "触发：被送到地下室平台。"
    event_details = {
        "event_awful_waffles": "力量检定（目标 4）失败受 1 点物理伤害。",
        "event_smoke": "速度检定（目标 4）失败：本回合移动停止。",
        "event_whoops": "速度检定（目标 4）失败：受 1 点物理伤害并结束移动。",
        "event_disquieting_sounds": "理智检定（目标 4）失败受 1 点精神伤害。",
        "event_spider": "速度检定（目标 3）失败受 1 点物理伤害。",
        "event_closet_door": "知识检定（目标 4）成功抽 1 张物品牌，失败受 1 点精神伤害。",
        "event_locked_safe": "知识检定（目标 5）成功抽 1 张物品牌，失败结束移动。",
        "event_groundskeeper": "知识检定（目标 4）成功抽 1 张物品牌。",
        "event_something_slimy": "力量检定（目标 4）失败失去 1 点速度。",
        "event_a_moment_of_hope": "选择恢复 1 点理智或知识。",
        "event_hanged_men": "理智检定（目标 4）失败受 1 点精神伤害并结束移动。",
        "event_jonahs_turn": "本回合获得 1 次额外检定重掷。",
        "event_it_is_meant_to_be": "保存一次掷骰结果；下一次检定时可选择使用。",
        "event_something_hidden": "知识检定（目标 4）成功抽 1 张物品牌。",
        "event_the_voice": "理智检定（目标 4）失败失去 1 点知识并回到地下室平台。",
        "event_webs": "力量检定（目标 4）失败：本回合移动停止。",
        "event_night_view": "理智检定（目标 4）成功获得 1 点速度，失败受 1 点精神伤害。",
        "event_creepy_crawlies": "力量检定（目标 4）失败受 1 点物理伤害并结束移动。",
        "event_phone_call": "选择恢复 1 点知识，或再抽 1 张事件牌并结束移动。",
    }
    if eid in event_details:
        return f"触发：{event_details[eid]}"

    # ------------------------------------------------------------ 通用兜底
    # 有属性加成
    for stat in STAT_ORDER:
        if bonus.get(stat):
            return f"被动：检定「{STAT_CN[stat]}」时 +{int(bonus[stat])}。"
    if "companion" in card.tags:
        return "同伴：不可交易/偷取，会一直跟随你。"
    if "weapon" in card.tags:
        return f"武器：攻击骰 +{attack}（作祟阶段攻击时生效）。"
    return ""


def card_short(card) -> str:
    """一句话短说明，适合在列表/面板里紧凑展示。"""
    usage = card_usage(card)
    if usage:
        return f"{card.name}：{usage}"
    return card.name


def room_effect_detail(effect_id: str) -> str:
    """返回房间特殊效果的一句话说明（覆盖所有已知 effect_id）。"""
    return ROOM_EFFECT_DETAIL.get(effect_id, "")


ROOM_EFFECT_DETAIL = {
    # 起始房间
    "room_start_hall": "起始房间（入口大厅），无特殊效果。",
    "room_start_foyer": "起始房间（门厅），无特殊效果。",
    "room_start_stairs": "起始房间（大楼梯），连接上下层。",
    "room_start_below": "起始房间（地下室平台），无特殊效果。",
    "room_start_above": "起始房间（二楼平台），无特殊效果。",
    # 有实际效果
    "room_chapel": "进入即触发：恢复 1 点理智。",
    "room_graveyard": "无特殊效果（进入时气氛让你不安，仅作背景）。",
    "room_gymnasium": "进入即触发：本回合移动步数 +1。",
    "room_library": "进入即触发：下一次检定额外获得一次重掷机会。",
    "room_larder": "进入即触发：恢复 1 点力量。",
    "room_research_laboratory": "进入时：进行知识检定（目标 4），通过则抽 1 张物品卡。",
    "room_bloody_room": "进入即触发：受到 1 点物理伤害。",
    "room_bedroom": "进入即触发：恢复 1 点理智。",
    "room_master_bedroom": "进入即触发：恢复 1 点理智。",
    "room_charred_room": "进入即触发：受到 1 点精神伤害。",
    "room_furnace_room": "进入即触发：受到 1 点物理伤害。",
    "room_coal_chute": "进入即触发：被送到地下室平台并结束移动。",
    "room_mystic_elevator": "进入时：掷骰前往随机楼层（叛徒可自选）。",
    "room_vault": "首次进入：知识检定（目标 4）通过抽 2 张物品卡，失败受 1 点物理伤害。",
    "room_chasm": "进入时：速度检定（目标 4）失败受 1 点物理伤害并停下。",
    "room_collapsed_room": "首次进入：受 1 点物理伤害并掉到地下室平台。",
    "room_tower": "进入时：速度检定（目标 4）失败受 1 点物理伤害。",
    "room_pentagram_chamber": "五芒星室：无常规特效，作祟阶段可能与仪式相关。",
    # 无特效但会触发符号卡
    "room_abandoned_room": "无特殊效果（进入触发房间符号卡）。",
    "room_ballroom": "无特殊效果（进入触发房间符号卡）。",
    "room_garden": "无特殊效果（进入触发房间符号卡）。",
    "room_junk_room": "无特殊效果（进入触发房间符号卡）。",
    "room_patio": "无特殊效果（进入触发房间符号卡）。",
    "room_conservatory": "无特殊效果（进入触发房间符号卡）。",
    "room_dining_room": "无特殊效果（进入触发房间符号卡）。",
    "room_gallery": "无特殊效果（进入触发房间符号卡）。",
    "room_operating_laboratory": "无特殊效果（进入触发房间符号卡）。",
    "room_servants_quarters": "无特殊效果（进入触发房间符号卡）。",
    "room_kitchen": "无特殊效果（进入触发房间符号卡）。",
    "room_balcony": "无特殊效果（进入触发房间符号卡）。",
    "room_organ_room": "无特殊效果（进入触发房间符号卡）。",
    "room_catacombs": "无特殊效果（进入触发房间符号卡）。",
    "room_crypt": "无特殊效果（进入触发房间符号卡）。",
    # 占位 / 其它
    "room_attic": "特殊房间：部分剧本中的失败检定可留在这里下回合重试。",
    "room_bathroom": "无基础常规特效；首次发现时照房间符号抽事件牌。",
    "room_game_room": "无基础常规特效；首次发现时照房间符号抽物品牌。",
    "room_inner_hall": "无基础常规特效。",
    "room_creaky_hallway": "无基础常规特效；部分剧本会把它作为关键房间。",
    "room_dusty_hallway": "无基础常规特效。",
    "room_statuary_corridor": "无基础常规特效；部分剧本会把它作为关键房间。",
    "room_crawlspace": "无基础常规特效。",
    "room_storeroom": "无基础常规特效；首次发现时照房间符号抽物品牌。",
    "room_underground_lake": "若在上层发现，房间塌落到地下室并结束移动。",
    "room_wine_cellar": "无基础常规特效；首次发现时照房间符号抽物品牌。",
    "room_stairs_from_basement": "楼梯房间：用于在地下室与一层之间移动。",
    "room_graveyard_alt": "无特殊效果。",
    "none": "",
}


# ---------------------------------------------------------------- 规则速查
def rules_text() -> str:
    """基本规则速查文本（帮助面板用）。"""
    return (
        "《山中小屋》基本规则速查\n"
        "=======================\n"
        "【阶段】\n"
        "探索阶段（EXPLORE）：玩家轮流探索房间、抽卡、涨预兆。\n"
        "作祟阶段（HAUNT）：抽到预兆后掷作祟检定，可能揭示叛徒与剧本，进入对抗。\n"
        "【回合】\n"
        "每回合你有「速度」点移动步数，可进入相邻房间；进新房间会停下。\n"
        "可进行：移动 / 使用物品 / 拾取 / 丢弃 / 交易 /（作祟阶段）攻击 / 结束回合。\n"
        "【检定】\n"
        "需要检定时：掷若干骰（骰子每颗 0/0/1/1/2/2），总和 ≥ 目标即成功。\n"
        "骰子数量 = 对应属性值 + 加成（上限 8）。失败可用重掷机会再试一次。\n"
        "【属性】\n"
        f"速度 {STAT_CN['speed']}：移动步数、速度检定。\n"
        f"力量 {STAT_CN['might']}：承受物理伤害、力量攻击。\n"
        f"理智 {STAT_CN['sanity']}：承受精神伤害、理智检定。\n"
        f"知识 {STAT_CN['knowledge']}：知识检定、部分攻击。\n"
        "属性以「卡尺轨道」显示：跌出轨道最左格（骷髅）即该项归 0。\n"
        "【死亡】\n"
        "任何一项属性降到 0，该角色立即死亡并掉落所有物品。\n"
        "【作祟】\n"
        "预兆卡会累加预兆数；作祟检定 < 预兆数时触发剧本。\n"
        "作祟后分为「英雄」与「叛徒」两阵营，按剧本目标决出胜负。\n"
        "【骰子】\n"
        "本游戏使用特制骰：每个六面骰为 0、0、1、1、2、2（没有大数字，靠数量堆结果）。\n"
    )
