from __future__ import annotations

import random
from typing import Iterable

try:
    from .models import (
        Catalog,
        Card,
        CharacterFace,
        Haunt,
        MonsterTemplate,
        RoomTemplate,
    )
    try:
        from .haunts_zh import HAUNT_TRANSLATIONS
    except ImportError:  # pragma: no cover - optional generated data
        HAUNT_TRANSLATIONS = {}
    try:
        from .haunt_rules import get_haunt_rule_override
    except ImportError:  # pragma: no cover - optional rule data
        def get_haunt_rule_override(haunt_id: int) -> dict:
            return {}
except ImportError:  # pragma: no cover - direct script execution
    from models import (  # type: ignore
        Catalog,
        Card,
        CharacterFace,
        Haunt,
        MonsterTemplate,
        RoomTemplate,
    )
    try:
        from haunts_zh import HAUNT_TRANSLATIONS  # type: ignore
    except ImportError:  # pragma: no cover - optional generated data
        HAUNT_TRANSLATIONS = {}
    try:
        from haunt_rules import get_haunt_rule_override  # type: ignore
    except ImportError:  # pragma: no cover - optional rule data
        def get_haunt_rule_override(haunt_id: int) -> dict:
            return {}


def character_face(
    *,
    card_id: str,
    face_index: int,
    name: str,
    source_name: str,
    stats: dict[str, int],
    stats_max: dict[str, int],
    birthday: str,
    aliases: Iterable[str] = (),
    flavor: str = "",
    stats_tracks: dict[str, list[int]] | None = None,
) -> dict:
    return {
        "id": f"{card_id}_{face_index}",
        "card_id": card_id,
        "face_index": face_index,
        "name": name,
        "source_name": source_name,
        "aliases": list(aliases),
        "birthday": birthday,
        "stats": dict(stats),
        "stats_max": dict(stats_max),
        "stats_tracks": dict(stats_tracks) if stats_tracks else {},
        "flavor": flavor,
    }


def card_def(
    *,
    card_id: str,
    kind: str,
    name: str,
    source_name: str,
    text: str,
    tags: Iterable[str] = (),
    effect_id: str = "generic",
    keep: bool = True,
    tradeable: bool = True,
    omen_trigger: bool = False,
    one_shot: bool = False,
    bonus: dict[str, int] | None = None,
    data: dict | None = None,
) -> dict:
    return {
        "id": card_id,
        "kind": kind,
        "name": name,
        "source_name": source_name,
        "text": text,
        "tags": tuple(tags),
        "effect_id": effect_id,
        "keep": keep,
        "tradeable": tradeable,
        "omen_trigger": omen_trigger,
        "one_shot": one_shot,
        "bonus": dict(bonus or {}),
        "data": dict(data or {}),
    }


def room_def(
    *,
    room_id: str,
    name: str,
    source_name: str,
    floor: int,
    doors: Iterable[str],
    symbol: str | None = None,
    effect_id: str = "none",
    text: str = "",
    special: bool = False,
    links: dict[str, str] | None = None,
    tags: Iterable[str] = (),
    generated: bool = False,
) -> dict:
    return {
        "id": room_id,
        "name": name,
        "source_name": source_name,
        "floor": floor,
        "doors": tuple(doors),
        "symbol": symbol,
        "effect_id": effect_id,
        "text": text,
        "special": special,
        "links": dict(links or {}),
        "tags": tuple(tags),
        "generated": generated,
    }


def haunt_def(
    *,
    haunt_id: int,
    name: str,
    traitor_rule: str = "revealer",
    hero_goal: str = "",
    traitor_goal: str = "",
    mode: str = "generic",
    trigger_hint: str = "",
    suggested_monsters: Iterable[str] = (),
    notes: str = "",
    rule_data: dict | None = None,
) -> dict:
    return {
        "id": haunt_id,
        "name": name,
        "traitor_rule": traitor_rule,
        "hero_goal": hero_goal,
        "traitor_goal": traitor_goal,
        "mode": mode,
        "trigger_hint": trigger_hint,
        "suggested_monsters": list(suggested_monsters),
        "notes": notes,
        "rule_data": dict(rule_data or {}),
    }


def monster_def(
    *,
    monster_id: str,
    name: str,
    source_name: str,
    speed: int,
    might: int,
    sanity: int = 0,
    knowledge: int = 0,
    tags: Iterable[str] = (),
    can_carry_items: bool = False,
    text: str = "",
) -> dict:
    return {
        "id": monster_id,
        "name": name,
        "source_name": source_name,
        "speed": speed,
        "might": might,
        "sanity": sanity,
        "knowledge": knowledge,
        "tags": tuple(tags),
        "can_carry_items": can_carry_items,
        "text": text,
    }


CHARACTER_FACES = [
    character_face(
        card_id="card_1",
        face_index=0,
        name="父亲 Rhinehardt",
        source_name="Father Rhinehardt",
        stats={"speed": 3, "might": 3, "sanity": 5, "knowledge": 4},
        stats_max={"speed": 4, "might": 4, "sanity": 6, "knowledge": 5},
        birthday="4/11",
        aliases=("Father Rhinehardt",),
        stats_tracks={
            "speed": [2, 3, 3, 4, 5, 6, 7, 7],
            "might": [1, 2, 2, 4, 4, 5, 5, 7],
            "sanity": [3, 4, 5, 5, 6, 7, 7, 8],
            "knowledge": [1, 3, 3, 4, 5, 6, 6, 8],
        },
    ),
    character_face(
        card_id="card_1",
        face_index=1,
        name="朗费洛教授",
        source_name="Professor Longfellow",
        stats={"speed": 2, "might": 3, "sanity": 4, "knowledge": 5},
        stats_max={"speed": 3, "might": 4, "sanity": 5, "knowledge": 6},
        birthday="1/8",
        aliases=("Professor Longfellow", "Professor Josiah Longfellow"),
        stats_tracks={
            "speed": [2, 2, 4, 4, 5, 5, 6, 6],
            "might": [1, 2, 3, 4, 5, 5, 6, 6],
            "sanity": [1, 3, 3, 4, 5, 5, 6, 7],
            "knowledge": [4, 5, 5, 5, 5, 6, 7, 8],
        },
    ),
    character_face(
        card_id="card_2",
        face_index=0,
        name="玛黛姆·佐斯特拉",
        source_name="Madame Zostra",
        stats={"speed": 3, "might": 3, "sanity": 5, "knowledge": 4},
        stats_max={"speed": 4, "might": 4, "sanity": 6, "knowledge": 5},
        birthday="9/30",
        aliases=("Madame Zostra", "Madame Belladina Zostra"),
        stats_tracks={
            "speed": [2, 3, 3, 5, 5, 6, 6, 7],
            "might": [2, 3, 3, 4, 5, 5, 5, 6],
            "sanity": [4, 4, 4, 5, 6, 7, 8, 8],
            "knowledge": [1, 3, 4, 4, 4, 5, 6, 6],
        },
    ),
    character_face(
        card_id="card_2",
        face_index=1,
        name="维维安·洛佩兹",
        source_name="Vivienne Lopez",
        stats={"speed": 4, "might": 2, "sanity": 4, "knowledge": 5},
        stats_max={"speed": 5, "might": 3, "sanity": 5, "knowledge": 6},
        birthday="6/20",
        aliases=("Vivian Lopez", "Vivienne Lopez"),
        stats_tracks={
            "speed": [3, 4, 4, 4, 4, 6, 7, 8],
            "might": [2, 2, 2, 4, 4, 5, 6, 6],
            "sanity": [4, 4, 4, 5, 6, 7, 8, 8],
            "knowledge": [4, 5, 5, 5, 5, 6, 6, 7],
        },
    ),
    character_face(
        card_id="card_3",
        face_index=0,
        name="布兰登·贾斯珀斯",
        source_name="Brandon Jaspers",
        stats={"speed": 4, "might": 4, "sanity": 3, "knowledge": 3},
        stats_max={"speed": 5, "might": 5, "sanity": 4, "knowledge": 4},
        birthday="2/17",
        aliases=("Brandon Jaspers",),
        stats_tracks={
            "speed": [3, 4, 4, 4, 5, 6, 7, 8],
            "might": [2, 3, 3, 4, 5, 6, 6, 7],
            "sanity": [3, 3, 3, 4, 5, 6, 7, 8],
            "knowledge": [1, 3, 3, 5, 5, 6, 6, 7],
        },
    ),
    character_face(
        card_id="card_3",
        face_index=1,
        name="米西·杜布尔德",
        source_name="Missy Dubourde",
        stats={"speed": 5, "might": 3, "sanity": 4, "knowledge": 3},
        stats_max={"speed": 6, "might": 4, "sanity": 5, "knowledge": 4},
        birthday="7/4",
        aliases=("Missy Dubourde",),
        stats_tracks={
            "speed": [3, 4, 5, 6, 6, 6, 7, 7],
            "might": [2, 3, 3, 3, 4, 5, 6, 7],
            "sanity": [1, 2, 3, 4, 5, 5, 6, 7],
            "knowledge": [2, 3, 4, 4, 5, 6, 6, 6],
        },
    ),
    character_face(
        card_id="card_4",
        face_index=0,
        name="佐伊·英格斯特伦",
        source_name="Zoe Ingstrom",
        stats={"speed": 6, "might": 2, "sanity": 4, "knowledge": 3},
        stats_max={"speed": 7, "might": 3, "sanity": 5, "knowledge": 4},
        birthday="10/5",
        aliases=("Zoe Ingstrom",),
        stats_tracks={
            "speed": [4, 4, 4, 4, 5, 6, 8, 8],
            "might": [2, 2, 3, 3, 4, 4, 6, 7],
            "sanity": [3, 4, 5, 5, 6, 6, 7, 8],
            "knowledge": [1, 2, 3, 4, 4, 5, 5, 5],
        },
    ),
    character_face(
        card_id="card_4",
        face_index=1,
        name="达林·威廉姆斯",
        source_name="Darrin Williams",
        stats={"speed": 5, "might": 4, "sanity": 3, "knowledge": 2},
        stats_max={"speed": 6, "might": 5, "sanity": 4, "knowledge": 3},
        birthday="3/23",
        aliases=("Darrin Williams",),
        stats_tracks={
            "speed": [4, 4, 4, 5, 6, 7, 7, 8],
            "might": [2, 3, 3, 4, 5, 6, 6, 7],
            "sanity": [1, 2, 3, 4, 5, 5, 5, 7],
            "knowledge": [2, 3, 3, 4, 5, 5, 5, 7],
        },
    ),
    character_face(
        card_id="card_5",
        face_index=0,
        name="奥克斯·贝洛斯",
        source_name="Ox Bellows",
        stats={"speed": 3, "might": 5, "sanity": 3, "knowledge": 2},
        stats_max={"speed": 4, "might": 6, "sanity": 4, "knowledge": 3},
        birthday="11/15",
        aliases=("Ox Bellows",),
        stats_tracks={
            "speed": [2, 2, 2, 3, 4, 5, 5, 6],
            "might": [4, 5, 5, 6, 6, 7, 8, 8],
            "sanity": [2, 2, 3, 4, 5, 5, 6, 7],
            "knowledge": [2, 2, 3, 3, 5, 5, 6, 6],
        },
    ),
    character_face(
        card_id="card_5",
        face_index=1,
        name="沃伦·梁",
        source_name="Warren Leung",
        stats={"speed": 4, "might": 3, "sanity": 4, "knowledge": 4},
        stats_max={"speed": 5, "might": 4, "sanity": 5, "knowledge": 5},
        birthday="12/1",
        aliases=("Warren Leung",),
        # 沃伦属于精神型角色；理智/知识在中后段有明显跳升，并有属性可达 8。
        stats_tracks={
            "speed": [2, 3, 4, 4, 5, 5, 6, 7],
            "might": [1, 2, 3, 3, 4, 4, 5, 6],
            "sanity": [2, 2, 3, 4, 4, 5, 7, 8],
            "knowledge": [1, 2, 3, 4, 5, 6, 6, 8],
        },
    ),
    character_face(
        card_id="card_6",
        face_index=0,
        name="希瑟·格兰维尔",
        source_name="Heather Granville",
        stats={"speed": 3, "might": 2, "sanity": 5, "knowledge": 5},
        stats_max={"speed": 4, "might": 3, "sanity": 6, "knowledge": 6},
        birthday="8/29",
        aliases=("Heather Granville",),
        stats_tracks={
            "speed": [3, 3, 4, 5, 6, 6, 7, 8],
            "might": [3, 3, 3, 4, 5, 6, 7, 8],
            "sanity": [3, 3, 3, 4, 5, 6, 6, 6],
            "knowledge": [2, 3, 3, 4, 5, 6, 7, 8],
        },
    ),
    character_face(
        card_id="card_6",
        face_index=1,
        name="珍妮·勒克莱尔",
        source_name="Jenny LeClerc",
        stats={"speed": 4, "might": 3, "sanity": 3, "knowledge": 4},
        stats_max={"speed": 5, "might": 4, "sanity": 4, "knowledge": 5},
        birthday="5/12",
        aliases=("Jenny LeClerc",),
        stats_tracks={
            "speed": [2, 3, 4, 4, 4, 5, 6, 8],
            "might": [3, 4, 4, 4, 4, 5, 6, 8],
            "sanity": [1, 1, 2, 4, 4, 4, 5, 6],
            "knowledge": [2, 3, 3, 4, 4, 5, 6, 8],
        },
    ),
]


OMEN_CARDS = [
    card_def(
        card_id="omen_bite",
        kind="omen",
        name="咬伤",
        source_name="Bite",
        text="这道咬痕会带来某种未知的诅咒。",
        tags=("omen", "curse"),
        effect_id="omen_bite",
        keep=True,
        tradeable=False,
        omen_trigger=True,
        bonus={},
    ),
    card_def(
        card_id="omen_book",
        kind="omen",
        name="书",
        source_name="Book",
        text="纸页里的知识会在检定时帮上忙。",
        tags=("omen", "knowledge_bonus"),
        effect_id="omen_book",
        keep=True,
        bonus={"knowledge": 2},
    ),
    card_def(
        card_id="omen_crystal_ball",
        kind="omen",
        name="水晶球",
        source_name="Crystal Ball",
        text="凝视它时，知识会变得更加敏锐。",
        tags=("omen", "knowledge_bonus", "reroll"),
        effect_id="omen_crystal_ball",
        keep=True,
        bonus={"knowledge": 2, "reroll": 1},
    ),
    card_def(
        card_id="omen_dog",
        kind="omen",
        name="狗",
        source_name="Dog",
        text="忠诚的同伴，会一直跟着你。",
        tags=("omen", "companion", "animal"),
        effect_id="omen_companion",
        keep=True,
        tradeable=False,
        bonus={},
    ),
    card_def(
        card_id="omen_girl",
        kind="omen",
        name="女孩",
        source_name="Girl",
        text="同伴卡，不能被交易或偷取。",
        tags=("omen", "companion", "animal"),
        effect_id="omen_companion",
        keep=True,
        tradeable=False,
    ),
    card_def(
        card_id="omen_holy_symbol",
        kind="omen",
        name="圣徽",
        source_name="Holy Symbol",
        text="信念让精神检定更稳定。",
        tags=("omen", "sanity_bonus", "holy"),
        effect_id="omen_holy_symbol",
        keep=True,
        bonus={"sanity": 2},
    ),
    card_def(
        card_id="omen_madman",
        kind="omen",
        name="疯子",
        source_name="Madman",
        text="某种程度上，这也是一个同伴。",
        tags=("omen", "companion", "insane"),
        effect_id="omen_companion",
        keep=True,
        tradeable=False,
    ),
    card_def(
        card_id="omen_mask",
        kind="omen",
        name="面具",
        source_name="Mask",
        text="它会在攻击时带来一点额外的胆量。",
        tags=("omen", "attack_bonus"),
        effect_id="omen_mask",
        keep=True,
        bonus={"attack": 1},
    ),
    card_def(
        card_id="omen_medallion",
        kind="omen",
        name="徽章",
        source_name="Medallion",
        text="这枚徽章带着一点安神的力量。",
        tags=("omen", "sanity_bonus"),
        effect_id="omen_medallion",
        keep=True,
        bonus={"sanity": 1},
    ),
    card_def(
        card_id="omen_ring",
        kind="omen",
        name="戒指",
        source_name="Ring",
        text="古旧而安静，像是把知识都收拢起来。",
        tags=("omen", "knowledge_bonus"),
        effect_id="omen_ring",
        keep=True,
        bonus={"knowledge": 1},
    ),
    card_def(
        card_id="omen_skull",
        kind="omen",
        name="头骨",
        source_name="Skull",
        text="冰冷的头骨，提醒你作祟已在路上。",
        tags=("omen", "omen_key"),
        effect_id="omen_skull",
        keep=True,
    ),
    card_def(
        card_id="omen_spear",
        kind="omen",
        name="长矛",
        source_name="Spear",
        text="长矛可以在攻击里额外带来力量。",
        tags=("omen", "weapon", "attack_bonus"),
        effect_id="omen_spear",
        keep=True,
        bonus={"attack": 2},
    ),
    card_def(
        card_id="omen_spirit_board",
        kind="omen",
        name="通灵板",
        source_name="Spirit Board",
        text="让知识与灵界的联系更紧密。",
        tags=("omen", "knowledge_bonus", "omen_key"),
        effect_id="omen_spirit_board",
        keep=True,
        bonus={"knowledge": 2},
    ),
]


ITEM_CARDS = [
    card_def(
        card_id="item_axe",
        kind="item",
        name="斧头",
        source_name="Axe",
        text="攻击时可增加额外的骰子。",
        tags=("item", "weapon"),
        effect_id="item_weapon",
        bonus={"attack": 2},
    ),
    card_def(
        card_id="item_blood_dagger",
        kind="item",
        name="血匕首",
        source_name="Blood Dagger",
        text="锋利得有些不讲道理。",
        tags=("item", "weapon", "blood"),
        effect_id="item_weapon_blood",
        bonus={"attack": 3},
        data={"self_damage": 1},
    ),
    card_def(
        card_id="item_dynamite",
        kind="item",
        name="炸药",
        source_name="Dynamite",
        text="一次性的大爆炸。",
        tags=("item", "weapon", "consumable"),
        effect_id="item_dynamite",
        one_shot=True,
        bonus={"attack": 4},
        data={"self_damage": 0},
    ),
    card_def(
        card_id="item_revolver",
        kind="item",
        name="左轮手枪",
        source_name="Revolver",
        text="可以远程攻击同一直线上的目标（速度攻击）。",
        tags=("item", "weapon", "ranged", "speed"),
        effect_id="item_revolver",
        bonus={"attack": 2},
    ),
    card_def(
        card_id="item_sacrificial_dagger",
        kind="item",
        name="献祭匕首",
        source_name="Sacrificial Dagger",
        text="强力武器，但代价不小。",
        tags=("item", "weapon", "blood"),
        effect_id="item_weapon_sacrifice",
        bonus={"attack": 4},
        data={"self_damage": 1},
    ),
    card_def(
        card_id="item_idol",
        kind="item",
        name="神像",
        source_name="Idol",
        text="允许一次检定重掷。",
        tags=("item", "reroll"),
        effect_id="item_reroll",
        bonus={"reroll": 1},
    ),
    card_def(
        card_id="item_lucky_stone",
        kind="item",
        name="幸运石",
        source_name="Lucky Stone",
        text="手感不错，可以重掷。",
        tags=("item", "reroll"),
        effect_id="item_reroll",
        bonus={"reroll": 1},
    ),
    card_def(
        card_id="item_rabbit_foot",
        kind="item",
        name="兔脚",
        source_name="Rabbit's Foot",
        text="也许会让你更走运一点。",
        tags=("item", "reroll"),
        effect_id="item_reroll",
        bonus={"reroll": 1},
    ),
    card_def(
        card_id="item_healing_salve",
        kind="item",
        name="治疗药膏",
        source_name="Healing Salve",
        text="恢复一点身体损伤。",
        tags=("item", "heal"),
        effect_id="item_heal_small",
        data={"heal": 1, "kind": "physical"},
    ),
    card_def(
        card_id="item_medical_kit",
        kind="item",
        name="医疗包",
        source_name="Medical Kit",
        text="比药膏更好用一些。",
        tags=("item", "heal"),
        effect_id="item_heal_large",
        data={"heal": 2, "kind": "physical"},
    ),
    card_def(
        card_id="item_smelling_salts",
        kind="item",
        name="嗅盐",
        source_name="Smelling Salts",
        text="用来缓和精神损伤。",
        tags=("item", "heal"),
        effect_id="item_heal_sanity",
        data={"heal": 1, "kind": "mental"},
    ),
    card_def(
        card_id="item_adrenaline_shot",
        kind="item",
        name="肾上腺素针",
        source_name="Adrenaline Shot",
        text="这一回合能跑得更快。",
        tags=("item", "speed"),
        effect_id="item_adrenaline",
        one_shot=True,
        data={"speed_bonus": 3},
    ),
    card_def(
        card_id="item_angel_feather",
        kind="item",
        name="天使羽毛",
        source_name="Angel Feather",
        text="下一次检定自动成功。",
        tags=("item", "check"),
        effect_id="item_angel_feather",
        one_shot=True,
        data={"auto_success": True},
    ),
    card_def(
        card_id="item_armor",
        kind="item",
        name="盔甲",
        source_name="Armor",
        text="可以挡住一次物理伤害。",
        tags=("item", "armor"),
        effect_id="item_armor",
        tradeable=False,
        data={"blocks_physical": True},
    ),
    card_def(
        card_id="item_bell",
        kind="item",
        name="铃铛",
        source_name="Bell",
        text="安神，也许还有别的用途。",
        tags=("item", "sanity_bonus"),
        effect_id="item_bell",
        bonus={"sanity": 1},
    ),
    card_def(
        card_id="item_candle",
        kind="item",
        name="蜡烛",
        source_name="Candle",
        text="在知识攻击里会更顺手。",
        tags=("item", "knowledge_bonus", "weapon"),
        effect_id="item_candle",
        bonus={"knowledge": 1, "attack": 1},
    ),
    card_def(
        card_id="item_music_box",
        kind="item",
        name="音乐盒",
        source_name="Music Box",
        text="可以让怪物暂停一会儿。",
        tags=("item", "control"),
        effect_id="item_music_box",
        data={"stun": 2},
    ),
    card_def(
        card_id="item_bottle",
        kind="item",
        name="瓶子",
        source_name="Bottle",
        text="随机影响属性。",
        tags=("item", "random"),
        effect_id="item_bottle",
        one_shot=True,
        data={"random_shift": 1},
    ),
    card_def(
        card_id="item_dark_dice",
        kind="item",
        name="黑暗骰子",
        source_name="Dark Dice",
        text="可重复使用的随机道具。",
        tags=("item", "random"),
        effect_id="item_dark_dice",
        data={"random_shift": 1, "repeatable": True},
    ),
    card_def(
        card_id="item_amulet_of_the_ages",
        kind="item",
        name="远古护身符",
        source_name="Amulet of the Ages",
        text="可以提升一项属性。",
        tags=("item", "boost"),
        effect_id="item_amulet",
        data={"stat_boost": 1},
    ),
    card_def(
        card_id="item_pickpockets_gloves",
        kind="item",
        name="扒手手套",
        source_name="Pickpocket's Gloves",
        text="偷一件物品。",
        tags=("item", "steal"),
        effect_id="item_pickpocket",
        data={"steal_item": True},
    ),
    card_def(
        card_id="item_puzzle_box",
        kind="item",
        name="谜题盒",
        source_name="Puzzle Box",
        text="每回合可以尝试打开一次。",
        tags=("item", "draw"),
        effect_id="item_puzzle_box",
        data={"draw_items": 2},
    ),
]


EVENT_BASES = [
    card_def(
        card_id="event_awful_waffles",
        kind="event",
        name="可怕的华夫饼",
        source_name="Awful Waffles",
        text="又甜又诡异。",
        tags=("event",),
        effect_id="event_awful_waffles",
        keep=False,
    ),
    card_def(
        card_id="event_bloody_vision",
        kind="event",
        name="血腥幻象",
        source_name="Bloody Vision",
        text="一次精神检定，失败会带来麻烦。",
        tags=("event", "check"),
        effect_id="event_bloody_vision",
        keep=False,
    ),
    card_def(
        card_id="event_grave_dirt",
        kind="event",
        name="坟墓泥土",
        source_name="Grave Dirt",
        text="脚下的土会一直纠缠着你。",
        tags=("event", "damage"),
        effect_id="event_grave_dirt",
        keep=False,
    ),
    card_def(
        card_id="event_lights_out",
        kind="event",
        name="熄灯",
        source_name="Lights Out",
        text="这一回合你的速度会被压低。",
        tags=("event", "speed"),
        effect_id="event_lights_out",
        keep=False,
    ),
    card_def(
        card_id="event_mists_from_the_walls",
        kind="event",
        name="墙中迷雾",
        source_name="Mists From The Walls",
        text="墙里涌出的雾气会让地下室更危险。",
        tags=("event", "basement"),
        effect_id="event_mists_from_the_walls",
        keep=False,
    ),
    card_def(
        card_id="event_mystic_slide",
        kind="event",
        name="神秘滑道",
        source_name="Mystic Slide",
        text="滑向地下室。",
        tags=("event", "move"),
        effect_id="event_mystic_slide",
        keep=False,
    ),
    card_def(
        card_id="event_secret_passage",
        kind="event",
        name="密道",
        source_name="Secret Passage",
        text="连接两个房间。",
        tags=("event", "link"),
        effect_id="event_secret_passage",
        keep=False,
    ),
    card_def(
        card_id="event_secret_stairs",
        kind="event",
        name="秘密楼梯",
        source_name="Secret Stairs",
        text="让楼层之间多一条通路。",
        tags=("event", "link"),
        effect_id="event_secret_stairs",
        keep=False,
    ),
    card_def(
        card_id="event_silence",
        kind="event",
        name="寂静",
        source_name="Silence",
        text="地下室的安静会像压力一样压下来。",
        tags=("event", "basement"),
        effect_id="event_silence",
        keep=False,
    ),
    card_def(
        card_id="event_lost_one",
        kind="event",
        name="迷失者",
        source_name="The Lost One",
        text="把你送到更低的地方。",
        tags=("event", "move"),
        effect_id="event_lost_one",
        keep=False,
    ),
    card_def(
        card_id="event_the_walls",
        kind="event",
        name="墙壁",
        source_name="The Walls",
        text="墙壁会把你往地下室推。",
        tags=("event", "move"),
        effect_id="event_the_walls",
        keep=False,
    ),
]


ROOM_BASES = [
    room_def(
        room_id="basement_landing",
        name="地下室平台",
        source_name="Basement Landing",
        floor=-1,
        doors=("north", "east", "west"),
        special=True,
        effect_id="room_start_below",
        text="地下室楼梯入口。探索地下层的起点。",
        links={"up": "entrance_hall"},
    ),
    room_def(
        room_id="entrance_hall",
        name="入口大厅",
        source_name="Entrance Hall",
        floor=0,
        doors=("east", "west", "south"),
        special=True,
        effect_id="room_start_hall",
        text="前门紧锁着，房屋的正门厅。",
        links={"down": "basement_landing"},
    ),
    room_def(
        room_id="foyer",
        name="门厅",
        source_name="Foyer",
        floor=0,
        doors=("west", "east", "south"),
        special=True,
        effect_id="room_start_foyer",
        text="门厅连接着老屋更深的区域。",
        links={},
    ),
    room_def(
        room_id="grand_staircase",
        name="大楼梯",
        source_name="Grand Staircase",
        floor=0,
        doors=("west", "east", "north"),
        special=True,
        effect_id="room_start_stairs",
        text="楼梯通向上层。",
        links={"up": "upper_landing"},
    ),
    room_def(
        room_id="upper_landing",
        name="二楼平台",
        source_name="Upper Landing",
        floor=1,
        doors=("south", "east", "west"),
        special=True,
        effect_id="room_start_above",
        text="二楼的起点。",
        links={"down": "grand_staircase"},
    ),
    room_def(
        room_id="catacombs",
        name="地下墓穴",
        source_name="Catacombs",
        floor=-1,
        doors=("north", "east", "west"),
        symbol="omen",
        effect_id="room_catacombs",
        text="阴冷而潮湿，埋着许多不想被提起的东西。",
    ),
    room_def(
        room_id="crypt",
        name="地窖",
        source_name="Crypt",
        floor=-1,
        doors=("north", "east", "south"),
        symbol="omen",
        effect_id="room_crypt",
        text="低矮、沉闷，空气几乎不会流动。",
    ),
    room_def(
        room_id="furnace_room",
        name="熔炉房",
        source_name="Furnace Room",
        floor=-1,
        doors=("north", "west", "south"),
        symbol="event",
        effect_id="room_furnace_room",
        text="炉膛里残留着炭灰和热意。",
    ),
    room_def(
        room_id="stairs_from_basement",
        name="地下室楼梯",
        source_name="Stairs from Basement",
        floor=-1,
        doors=("north", "east", "west"),
        special=True,
        effect_id="room_stairs_from_basement",
        text="一段连接到楼上的楼梯。",
        links={"up": "entrance_hall"},
    ),
    room_def(
        room_id="vault",
        name="保险库",
        source_name="Vault",
        floor=-1,
        doors=("north", "east", "west"),
        special=True,
        effect_id="room_vault",
        text="厚重的保险库门会挡住去路。",
    ),
    room_def(
        room_id="coal_chute",
        name="煤导槽",
        source_name="Coal Chute",
        floor=-1,
        doors=("north", "east"),
        special=True,
        effect_id="room_coal_chute",
        text="从这里可以直接滑向地下室入口。",
    ),
    room_def(
        room_id="abandoned_room",
        name="废弃房间",
        source_name="Abandoned Room",
        floor=0,
        doors=("north", "east", "west"),
        symbol="event",
        effect_id="room_abandoned_room",
        text="墙角堆着被遗忘的破旧家具。",
    ),
    room_def(
        room_id="ballroom",
        name="舞厅",
        source_name="Ballroom",
        floor=0,
        doors=("north", "east", "west"),
        symbol="event",
        effect_id="room_ballroom",
        text="地板空旷，像是等着一场没人愿意参加的舞会。",
    ),
    room_def(
        room_id="bloody_room",
        name="血房间",
        source_name="Bloody Room",
        floor=0,
        doors=("north", "east", "south"),
        symbol="event",
        effect_id="room_bloody_room",
        text="墙壁和地板上都有干涸的痕迹。",
    ),
    room_def(
        room_id="chapel",
        name="小教堂",
        source_name="Chapel",
        floor=0,
        doors=("west", "east", "south"),
        symbol="omen",
        effect_id="room_chapel",
        text="这里安静得让人不敢大声呼吸。",
    ),
    room_def(
        room_id="conservatory",
        name="温室",
        source_name="Conservatory",
        floor=0,
        doors=("north", "east", "south"),
        symbol="item",
        effect_id="room_conservatory",
        text="植物的气味比你记得的还要浓。",
    ),
    room_def(
        room_id="dining_room",
        name="餐厅",
        source_name="Dining Room",
        floor=0,
        doors=("north", "east", "west"),
        symbol="item",
        effect_id="room_dining_room",
        text="桌面上像是曾经摆过一场宴席。",
    ),
    room_def(
        room_id="garden",
        name="花园",
        source_name="Garden",
        floor=0,
        doors=("north", "east", "west"),
        symbol="event",
        effect_id="room_garden",
        text="花园已经失去最初的秩序。",
    ),
    room_def(
        room_id="graveyard",
        name="墓地",
        source_name="Graveyard",
        floor=0,
        doors=("north", "east", "south"),
        symbol="omen",
        effect_id="room_graveyard",
        text="这里让人本能地压低声音。",
    ),
    room_def(
        room_id="gymnasium",
        name="健身房",
        source_name="Gymnasium",
        floor=0,
        doors=("north", "east", "south"),
        symbol="event",
        effect_id="room_gymnasium",
        text="器械上积着厚厚的灰。",
    ),
    room_def(
        room_id="junk_room",
        name="杂物间",
        source_name="Junk Room",
        floor=0,
        doors=("north", "east", "west"),
        symbol="event",
        effect_id="room_junk_room",
        text="堆满杂物，但也许藏着能用的东西。",
    ),
    room_def(
        room_id="kitchen",
        name="厨房",
        source_name="Kitchen",
        floor=0,
        doors=("north", "east", "south"),
        symbol="item",
        effect_id="room_kitchen",
        text="锅具和刀叉都在，却没有人气。",
    ),
    room_def(
        room_id="library",
        name="图书馆",
        source_name="Library",
        floor=0,
        doors=("north", "east", "west"),
        symbol="item",
        effect_id="room_library",
        text="书架里有很多空白处。",
    ),
    room_def(
        room_id="larder",
        name="储藏室",
        source_name="Larder",
        floor=0,
        doors=("north", "east", "west"),
        symbol="item",
        effect_id="room_larder",
        text="食材和补给都藏在这里。",
    ),
    room_def(
        room_id="mystic_elevator",
        name="神秘电梯",
        source_name="Mystic Elevator",
        floor=0,
        doors=("north", "east", "south"),
        special=True,
        effect_id="room_mystic_elevator",
        text="进入后也许会被送到另一层。",
    ),
    room_def(
        room_id="organ_room",
        name="风琴房",
        source_name="Organ Room",
        floor=0,
        doors=("north", "west", "south"),
        symbol="omen",
        effect_id="room_organ_room",
        text="破旧的风琴还在占着角落。",
    ),
    room_def(
        room_id="patio",
        name="庭院",
        source_name="Patio",
        floor=0,
        doors=("north", "east", "west"),
        symbol="event",
        effect_id="room_patio",
        text="庭院开阔，却并不让人安心。",
    ),
    room_def(
        room_id="research_laboratory",
        name="研究实验室",
        source_name="Research Laboratory",
        floor=0,
        doors=("north", "east", "south"),
        symbol="item",
        effect_id="room_research_laboratory",
        text="一些器材还在发出微弱的滴答声。",
    ),
    room_def(
        room_id="chasm",
        name="深渊",
        source_name="Chasm",
        floor=0,
        doors=("north", "east", "west"),
        special=True,
        effect_id="room_chasm",
        text="脚下是裂开的黑暗。",
    ),
    room_def(
        room_id="pentagram_chamber",
        name="五芒星室",
        source_name="Pentagram Chamber",
        floor=0,
        doors=("north", "east", "west"),
        symbol="omen",
        effect_id="room_pentagram_chamber",
        text="地面上有残留的仪式痕迹。",
    ),
    room_def(
        room_id="balcony",
        name="阳台",
        source_name="Balcony",
        floor=1,
        doors=("south", "east", "west"),
        symbol="event",
        effect_id="room_balcony",
        text="从这里能看到屋外的夜色。",
    ),
    room_def(
        room_id="bedroom",
        name="卧室",
        source_name="Bedroom",
        floor=1,
        doors=("north", "east", "west"),
        symbol="item",
        effect_id="room_bedroom",
        text="床铺看上去像是刚被整理过。",
    ),
    room_def(
        room_id="charred_room",
        name="烧焦的房间",
        source_name="Charred Room",
        floor=1,
        doors=("north", "east", "south"),
        symbol="event",
        effect_id="room_charred_room",
        text="墙面有难看的黑痕。",
    ),
    room_def(
        room_id="collapsed_room",
        name="坍塌的房间",
        source_name="Collapsed Room",
        floor=1,
        doors=("north", "east", "west"),
        special=True,
        effect_id="room_collapsed_room",
        text="地板有一大片坍塌的洞口。",
    ),
    room_def(
        room_id="gallery",
        name="画廊",
        source_name="Gallery",
        floor=1,
        doors=("north", "east", "west"),
        symbol="item",
        effect_id="room_gallery",
        text="画框里的人物像在看着你。",
    ),
    room_def(
        room_id="master_bedroom",
        name="主卧",
        source_name="Master Bedroom",
        floor=1,
        doors=("north", "east", "west"),
        symbol="omen",
        effect_id="room_master_bedroom",
        text="这间卧室的气氛比其他地方更沉。",
    ),
    room_def(
        room_id="operating_laboratory",
        name="手术室",
        source_name="Operating Laboratory",
        floor=1,
        doors=("north", "east", "south"),
        symbol="item",
        effect_id="room_operating_laboratory",
        text="不该出现的器械整齐地摆着。",
    ),
    room_def(
        room_id="servants_quarters",
        name="仆人宿舍",
        source_name="Servants' Quarters",
        floor=1,
        doors=("north", "east", "south"),
        symbol="event",
        effect_id="room_servants_quarters",
        text="这里曾经很拥挤。",
    ),
    room_def(
        room_id="tower",
        name="塔楼",
        source_name="Tower",
        floor=1,
        doors=("north", "east", "west"),
        special=True,
        effect_id="room_tower",
        text="高处风大，视线却格外清楚。",
    ),
]


EVENT_SUPPLEMENTAL_SPECS = [
    ("event_shrieking_wind", "尖啸之风", "Shrieking Wind", "event_lights_out"),
    ("event_smoke", "烟雾", "Smoke", "event_smoke"),
    ("event_whoops", "糟了", "Whoops", "event_whoops"),
    ("event_drip_drip_drip", "滴答滴答滴答", "Drip Drip Drip", "event_grave_dirt"),
    ("event_possession", "附身", "Possession", "event_bloody_vision"),
    ("event_disquieting_sounds", "不安之声", "Disquieting Sounds", "event_disquieting_sounds"),
    ("event_spider", "蜘蛛", "Spider", "event_spider"),
    ("event_closet_door", "柜门", "Closet Door", "event_closet_door"),
    ("event_locked_safe", "上锁保险箱", "Locked Safe", "event_locked_safe"),
    ("event_rotten", "腐烂", "Rotten", "event_grave_dirt"),
    ("event_revolving_wall", "旋转墙", "Revolving Wall", "event_secret_passage"),
    ("event_creepy_puppet", "诡异木偶", "Creepy Puppet", "event_bloody_vision"),
    ("event_burning_man", "燃烧人影", "Burning Man", "event_grave_dirt"),
    ("event_image_in_the_mirror_backwards", "镜中倒影（反转）", "Image in the Mirror (Backwards)", "event_bloody_vision"),
    ("event_angry_being", "愤怒的存在", "Angry Being", "event_bloody_vision"),
    ("event_groundskeeper", "园丁", "Groundskeeper", "event_groundskeeper"),
    ("event_something_slimy", "黏滑之物", "Something Slimy", "event_something_slimy"),
    ("event_a_moment_of_hope", "希望一瞬", "A Moment of Hope", "event_a_moment_of_hope"),
    ("event_hanged_men", "吊尸", "Hanged Men", "event_hanged_men"),
    ("event_jonahs_turn", "乔纳的回合", "Jonah's Turn", "event_jonahs_turn"),
    ("event_it_is_meant_to_be", "命中注定", "It Is Meant to be", "event_it_is_meant_to_be"),
    ("event_something_hidden", "暗藏之物", "Something Hidden", "event_something_hidden"),
    ("event_debris", "瓦砾", "Debris", "event_lost_one"),
    ("event_funeral", "葬礼", "Funeral", "event_grave_dirt"),
    ("event_the_voice", "声音", "The Voice", "event_the_voice"),
    ("event_the_beckoning", "召唤", "The Beckoning", "event_lost_one"),
    ("event_image_in_the_mirror", "镜中倒影", "Image in the Mirror", "event_bloody_vision"),
    ("event_hideous_shriek", "可怖尖叫", "Hideous Shriek", "event_bloody_vision"),
    ("event_webs", "蛛网", "Webs", "event_webs"),
    ("event_night_view", "夜景", "Night View", "event_night_view"),
    ("event_creepy_crawlies", "虫影", "Creepy Crawlies", "event_creepy_crawlies"),
    ("event_footsteps", "脚步声", "Footsteps", "event_lost_one"),
    ("event_phone_call", "电话", "Phone Call", "event_phone_call"),
    ("event_skeletons", "骸骨", "Skeletons", "event_grave_dirt"),
]

ROOM_SUPPLEMENTAL_SPECS = [
    ("attic", "阁楼", "Attic", 1, ("south", "east", "west"), "event", "room_attic", True),
    ("bathroom", "浴室", "Bathroom", 1, ("north", "south"), "event", "room_bathroom", False),
    ("game_room", "游戏室", "Game Room", 1, ("north", "east", "south"), "item", "room_game_room", False),
    ("inner_hall", "内庭", "Inner Hall", 0, ("north", "east", "west"), None, "room_inner_hall", False),
    ("creaky_hallway", "吱呀走廊", "Creaky Hallway", -1, ("north", "south", "east"), None, "room_creaky_hallway", False),
    ("dusty_hallway", "积尘走廊", "Dusty Hallway", -1, ("east", "west"), None, "room_dusty_hallway", False),
    ("statuary_corridor", "雕像走廊", "Statuary Corridor", -1, ("north", "south", "west"), None, "room_statuary_corridor", False),
    ("crawlspace", "爬行空间", "Crawlspace", -1, ("north", "east"), None, "room_crawlspace", False),
    ("storeroom", "储藏室", "Storeroom", 1, ("north", "east"), "item", "room_storeroom", False),
    ("underground_lake", "地下湖", "Underground Lake", -1, ("north", "east", "west"), None, "room_underground_lake", True),
    ("wine_cellar", "酒窖", "Wine Cellar", -1, ("south", "east", "west"), "item", "room_wine_cellar", False),
]


def _event_spec_text(name: str, effect_id: str) -> str:
    if effect_id == "event_bloody_vision":
        return f"{name} 逼得你先稳住心神。"
    if effect_id == "event_grave_dirt":
        return f"{name} 像一团阴冷的污秽直接粘上来。"
    if effect_id == "event_lights_out":
        return f"{name} 让整栋房子忽然暗了下来。"
    if effect_id == "event_mists_from_the_walls":
        return f"{name} 会把地下室变得更危险。"
    if effect_id == "event_mystic_slide":
        return f"{name} 会把你直接拖回地下室。"
    if effect_id == "event_secret_passage":
        return f"{name} 似乎在楼层之间开出一条暗道。"
    if effect_id == "event_secret_stairs":
        return f"{name} 在房子里悄悄连出一组楼梯。"
    if effect_id == "event_silence":
        return f"{name} 让地下室的空气更压抑。"
    if effect_id in {"event_lost_one", "event_the_walls"}:
        return f"{name} 把你推向屋子的另一头。"
    return {
        "event_awful_waffles": "吃下这份诡异的食物前，先进行一次力量检定（目标 4）；失败受 1 点物理伤害。",
        "event_smoke": "烟雾遮住出口：进行速度检定（目标 4），失败则本回合移动停止。",
        "event_whoops": "脚下一滑：进行速度检定（目标 4），失败受 1 点物理伤害并结束移动。",
        "event_disquieting_sounds": "不安的声音逼近：进行理智检定（目标 4），失败受 1 点精神伤害。",
        "event_spider": "一只蜘蛛扑来：进行速度检定（目标 3），失败受 1 点物理伤害。",
        "event_closet_door": "柜门后藏着东西：进行知识检定（目标 4），成功抽 1 张物品牌，失败受 1 点精神伤害。",
        "event_locked_safe": "保险箱需要密码：进行知识检定（目标 5），成功抽 1 张物品牌，失败结束移动。",
        "event_groundskeeper": "园丁留下了可用的补给：进行知识检定（目标 4），成功抽 1 张物品牌。",
        "event_something_slimy": "黏滑的东西缠住了你：进行力量检定（目标 4），失败失去 1 点速度。",
        "event_a_moment_of_hope": "短暂的希望稳定了心神：恢复 1 点理智或知识。",
        "event_hanged_men": "吊影在眼前晃动：进行理智检定（目标 4），失败受 1 点精神伤害并结束移动。",
        "event_jonahs_turn": "乔纳替你看清了下一步：本回合获得 1 次额外检定重掷。",
        "event_it_is_meant_to_be": "记住这次结果：下一次检定前可选择使用本次掷骰结果。",
        "event_something_hidden": "发现隐藏的夹层：进行知识检定（目标 4），成功抽 1 张物品牌。",
        "event_the_voice": "声音在耳边低语：进行理智检定（目标 4），失败失去 1 点知识并被送回地下室平台。",
        "event_webs": "蛛网封住了通道：进行力量检定（目标 4），失败本回合移动停止。",
        "event_night_view": "窗外的景象令人屏息：进行理智检定（目标 4），成功获得 1 点速度，失败受 1 点精神伤害。",
        "event_creepy_crawlies": "虫子爬过皮肤：进行力量检定（目标 4），失败受 1 点物理伤害并结束移动。",
        "event_phone_call": "电话突然响起：选择恢复 1 点知识，或立刻抽 1 张事件牌并结束移动。",
    }.get(effect_id, f"{name} 会让这一回合的局势突然变糟。")


def _room_spec_text(name: str, symbol: str | None, effect_id: str) -> str:
    if effect_id == "room_underground_lake":
        return f"{name} 的水面通向房屋下方；若在上层发现，会塌落到地下室。"
    if effect_id == "room_attic":
        return f"{name} 是特殊房间：部分剧本中的失败检定可以留在这里下回合重试。"
    if symbol == "item":
        return f"{name} 里有物品符号，首次发现时抽 1 张物品牌。"
    if symbol == "event":
        return f"{name} 有事件符号，首次发现时抽 1 张事件牌。"
    if symbol == "omen":
        return f"{name} 有预兆符号，首次发现时抽 1 张预兆牌。"
    return f"{name} 没有基础规则中的常规特效；特殊剧本可能会改变它的作用。"


def _haunt_profile(name: str) -> tuple[str, str, str, list[str], str]:
    lower = name.lower()

    if any(token in lower for token in ("mummy", "tomb", "skeletal", "skull")):
        return (
            "lowest_sanity",
            "封住墓穴和遗骸，在复苏前把仪式拆掉。",
            "把墓中的旧主带回屋里，让所有人都晚一步。",
            ["mummy"],
            "围绕墓葬、遗骸和古老诅咒展开。",
        )
    if any(token in lower for token in ("ghost", "wraith", "phantom", "seance", "spirit")):
        return (
            "lowest_sanity",
            "切断通灵媒介，把屋里的灵体重新赶回黑暗。",
            "让亡者借房屋落地，并逼英雄接受它。",
            ["ghost"],
            "围绕降灵、幻影与亡灵回响展开。",
        )
    if any(token in lower for token in ("beast", "wolf", "lycanthrope", "ape", "bogeyman", "spider", "web", "crawling horror")):
        monster = "spider" if any(token in lower for token in ("spider", "web")) else "beast"
        return (
            "highest_might",
            "守住每个出口，别让巢穴和兽性吞掉屋子。",
            "让猎手和猎物的位置彻底翻转。",
            [monster],
            "围绕兽化、巢群或爬行恐惧展开。",
        )
    if any(token in lower for token in ("ivy", "plant", "rot", "feast", "dead", "skeletons")):
        return (
            "revealer",
            "阻止腐败、藤蔓或饥饿把房子整个吞下去。",
            "让腐烂和饥饿继续扩散到最后一间房。",
            ["plant"],
            "围绕腐败、藤蔓和死亡盛宴展开。",
        )
    if any(token in lower for token in ("ring", "medallion", "book", "mask", "spear", "crystal ball", "spirit board", "girl", "dog", "madman", "heir")):
        rule = "specific_character" if any(token in lower for token in ("girl", "dog", "madman", "heir")) else "revealer"
        return (
            rule,
            "围绕关键道具和人物抢在仪式完成前反制。",
            "凑齐需要的东西，把私愿推到终点。",
            ["shadow"],
            "围绕道具、同伴和身份压力展开。",
        )
    if any(token in lower for token in ("wall", "stairs", "slide", "elevator", "abyss", "chasm", "storm", "feast", "sacrifice", "piper", "stars", "again", "house")):
        return (
            "revealer",
            "找出房屋结构的破绽，在它合拢前撑住局面。",
            "让房子本身变成你的武器。",
            ["shadow"],
            "围绕房屋结构、空间转移和终局崩坏展开。",
        )

    return (
        "revealer",
        f"阻止《{name}》的计划成真。",
        f"让《{name}》的力量完全苏醒。",
        [],
        f"主题摘要：{name}",
    )


HAUNT_NAMES = [
    (1, "The Mummy Walks"),
    (2, "The Séance"),
    (3, "Frog-Leg Stew"),
    (4, "The Web of Destiny"),
    (5, "I Was a Teenage Lycanthrope"),
    (6, "The Floating Eye"),
    (7, "Carnivorous Ivy"),
    (8, "Wail of the Banshee"),
    (9, "The Dance of Death"),
    (10, "Family Gathering"),
    (11, "Let Them In"),
    (12, "Fleshwalkers"),
    (13, "Perchance to Dream"),
    (14, "The Stars Are Right"),
    (15, "Here There Be Dragons"),
    (16, "The Phantom’s Embrace"),
    (17, "Bugs"),
    (18, "Offspring"),
    (19, "The Beastmaster"),
    (20, "Ghost Bride"),
    (21, "House of the Living Dead"),
    (22, "The Abyss Gazes Back"),
    (23, "Tentacled Horror"),
    (24, "Fly Away Home"),
    (25, "Voodoo"),
    (26, "Pay the Piper"),
    (27, "Amok Flesh"),
    (28, "Ring of King Solomon"),
    (29, "Frankenstein’s Legacy"),
    (30, "Tomb of Dracula"),
    (31, "It’s Alive!"),
    (32, "Lost"),
    (33, "Creature from the Lake"),
    (34, "Mad, Mad World"),
    (35, "Small Change"),
    (36, "Better with Friends"),
    (37, "Checkmate"),
    (38, "Hellbeasts"),
    (39, "The Heir"),
    (40, "Buried Alive"),
    (41, "Invisible Traitor"),
    (42, "Comes the Hero"),
    (43, "A Gathering of Shadows"),
    (44, "Death Doth Find Us All"),
    (45, "Tick, Tick, Tick"),
    (46, "The Feast"),
    (47, "Worm Ouroboros"),
    (48, "Stacked Like Cordwood"),
    (49, "You Wear It Well"),
    (50, "A Little Night Murder"),
    (51, "Darker than Night"),
    (52, "In a Crackling Aura"),
    (53, "Reeking of Death"),
    (54, "The Skull of Ar’Kanok"),
    (55, "The King’s Roads"),
    (56, "Time Waits for One Man"),
    (57, "A Friend for the Ages"),
    (58, "Nightfall"),
    (59, "For a Thousand Years"),
    (60, "The Burning Sands"),
    (61, "Eternal Glory"),
    (62, "Bag of Tricks"),
    (63, "The Twisting Nether"),
    (64, "An Offering of Blood"),
    (65, "A Breath of Wind"),
    (66, "Hell on Earth"),
    (67, "Once Upon a Time"),
    (68, "The Labyrinth"),
    (69, "Way of the Wisp"),
    (70, "With an Inhuman Cry"),
]


MONSTER_BASES = [
    monster_def(
        monster_id="mummy",
        name="木乃伊",
        source_name="Mummy",
        speed=2,
        might=4,
        text="行动缓慢，但相当难缠。",
        tags=("undead", "slow"),
    ),
    monster_def(
        monster_id="ghost",
        name="幽灵",
        source_name="Ghost",
        speed=3,
        might=3,
        text="穿过墙壁时毫无压力。",
        tags=("undead", "spectral"),
    ),
    monster_def(
        monster_id="beast",
        name="野兽",
        source_name="Beast",
        speed=4,
        might=4,
        text="会朝着最近的目标狂奔。",
        tags=("beast",),
    ),
    monster_def(
        monster_id="spider",
        name="蜘蛛",
        source_name="Spider",
        speed=4,
        might=2,
        text="速度很快，但力量有限。",
        tags=("animal",),
    ),
    monster_def(
        monster_id="cultist",
        name="邪教徒",
        source_name="Cultist",
        speed=3,
        might=2,
        text="会围着他们的目标打转。",
        tags=("human",),
    ),
    monster_def(
        monster_id="zombie",
        name="僵尸",
        source_name="Zombie",
        speed=2,
        might=3,
        text="看起来没有那么聪明。",
        tags=("undead",),
    ),
    monster_def(
        monster_id="zombie_lord",
        name="僵尸领主",
        source_name="Zombie Lord",
        speed=3,
        might=7,
        sanity=2,
        text="驱使僵尸的古老不死之主——只有持徽章者能伤到它。",
        tags=("undead", "haunt_specific"),
    ),
    monster_def(
        monster_id="shadow",
        name="阴影",
        source_name="Shadow",
        speed=3,
        might=2,
        text="像雾一样贴近目标。",
        tags=("undead", "spectral"),
    ),
    monster_def(
        monster_id="wolf",
        name="狼",
        source_name="Wolf",
        speed=4,
        might=3,
        text="会沿着最短路线接近。",
        tags=("animal",),
    ),
    monster_def(
        monster_id="bat",
        name="蝙蝠",
        source_name="Bat",
        speed=5,
        might=2,
        sanity=1,
        text="不正面攻击，而是贴到人身上吸血。",
        tags=("animal", "haunt_specific"),
    ),
    monster_def(
        monster_id="rat",
        name="老鼠",
        source_name="Rat",
        speed=3,
        might=2,
        sanity=1,
        text="成群出没，同房间的老鼠会合力扑击；受到任何伤害即死。",
        tags=("animal", "haunt_specific"),
    ),
    monster_def(
        monster_id="plant",
        name="邪恶植物",
        source_name="Evil Plant",
        speed=2,
        might=3,
        text="会从阴影里伸出枝条。",
        tags=("plant",),
    ),
    monster_def(
        monster_id="witch",
        name="女巫",
        source_name="Witch",
        speed=4,
        might=3,
        sanity=6,
        text="在凡人形态法术完成前无法被普通攻击杀死。",
        tags=("caster", "haunt_specific"),
    ),
    monster_def(
        monster_id="cat",
        name="猫",
        source_name="Cat",
        speed=3,
        might=3,
        sanity=2,
        text="会追逐被变成青蛙的英雄。",
        tags=("animal", "haunt_specific"),
    ),
    monster_def(
        monster_id="giant_spider",
        name="巨型蜘蛛",
        source_name="Giant Spider",
        speed=0,
        might=2,
        sanity=5,
        text="蛛卵孵化前会守着被困者。",
        tags=("animal", "haunt_specific"),
    ),
    monster_def(
        monster_id="dog",
        name="狗",
        source_name="Dog",
        speed=6,
        might=4,
        sanity=3,
        text="狼人作祟中由叛徒控制。",
        tags=("animal", "haunt_specific"),
    ),
    monster_def(
        monster_id="alien",
        name="外星人",
        source_name="Alien",
        speed=4,
        might=6,
        sanity=6,
        text="会用精神控制把英雄送上宇宙飞船。",
        tags=("alien", "haunt_specific"),
    ),
    monster_def(
        monster_id="creeper_tip",
        name="爬行物尖端",
        source_name="Creeper Tip",
        speed=2,
        might=5,
        sanity=3,
        text="根部固定，尖端会抓走英雄。",
        tags=("plant", "haunt_specific"),
    ),
    monster_def(
        monster_id="banshee",
        name="女妖",
        source_name="Banshee",
        speed=8,
        might=0,
        sanity=0,
        text="不能被普通攻击，只能通过驱魔解决。",
        tags=("undead", "spectral", "haunt_specific"),
    ),
    monster_def(
        monster_id="madman",
        name="疯子",
        source_name="Madman",
        speed=3,
        might=5,
        sanity=5,
        text="家族聚会中承受 5 点物理伤害后才会倒下。",
        tags=("human", "haunt_specific"),
    ),
    monster_def(
        monster_id="giant",
        name="巨人",
        source_name="Giant",
        speed=2,
        might=5,
        text="移动慢，但碰撞很疼。",
        tags=("beast",),
    ),
]


def _make_supplemental_rooms(
    rng: random.Random,
    room_templates: dict[str, dict],
    targets: dict[int, int],
    excluded_ids: set[str],
) -> list[dict]:
    added: list[dict] = []
    for floor, target in targets.items():
        current = sum(
            1
            for room_id, room in room_templates.items()
            if room["floor"] == floor and room_id not in excluded_ids
        )
        candidates = [spec for spec in ROOM_SUPPLEMENTAL_SPECS if spec[3] == floor]
        index = 1
        while current < target:
            if index - 1 >= len(candidates):
                break
            room_id, name, source_name, room_floor, doors, symbol, effect_id, special = candidates[index - 1]
            if room_id in room_templates:
                index += 1
                continue
            added.append(
                room_def(
                    room_id=room_id,
                    name=name,
                    source_name=source_name,
                    floor=room_floor,
                    doors=doors,
                    symbol=symbol,
                    effect_id=effect_id,
                    text=_room_spec_text(name, symbol, effect_id),
                    special=special,
                    generated=False,
                )
            )
            current += 1
            index += 1
    return added


def _make_supplemental_events(rng: random.Random, count: int) -> list[dict]:
    events: list[dict] = []
    for card_id, name, source_name, effect_id in EVENT_SUPPLEMENTAL_SPECS[:count]:
        events.append(
            card_def(
                card_id=card_id,
                kind="event",
                name=name,
                source_name=source_name,
                text=_event_spec_text(name, effect_id),
                tags=("event",),
                effect_id=effect_id,
                keep=False,
            )
        )
    rng.shuffle(events)
    return events


def build_catalog(seed: int | None = None) -> Catalog:
    rng = random.Random(seed)

    characters = {
        face["id"]: CharacterFace(**face)
        for face in CHARACTER_FACES
    }
    character_cards: dict[str, list[str]] = {}
    for face in CHARACTER_FACES:
        character_cards.setdefault(face["card_id"], []).append(face["id"])

    cards: dict[str, Card] = {}
    for spec in OMEN_CARDS + ITEM_CARDS + EVENT_BASES + _make_supplemental_events(rng, 45 - len(EVENT_BASES)):
        cards[spec["id"]] = Card(**spec)

    room_template_specs = ROOM_BASES[:]
    room_template_map: dict[str, dict] = {spec["id"]: spec for spec in room_template_specs}
    room_targets = {-1: 12, 0: 20, 1: 12}
    start_ids = {"basement_landing", "entrance_hall", "foyer", "grand_staircase", "upper_landing"}
    for spec in _make_supplemental_rooms(rng, room_template_map, room_targets, start_ids):
        room_template_specs.append(spec)
        room_template_map[spec["id"]] = spec

    room_templates = {spec["id"]: RoomTemplate(**spec) for spec in room_template_specs}
    room_draw_pool = [
        room_id
        for room_id, template in room_templates.items()
        if room_id not in start_ids
    ]
    rng.shuffle(room_draw_pool)

    haunt_defs: dict[int, Haunt] = {}
    for haunt_id, name in HAUNT_NAMES:
        rule, hero_goal, traitor_goal, monsters, notes = _haunt_profile(name)
        translation = HAUNT_TRANSLATIONS.get(str(haunt_id), HAUNT_TRANSLATIONS.get(haunt_id, {}))
        rule_data = get_haunt_rule_override(haunt_id)
        if rule_data:
            rule = rule_data.get("traitor_rule", rule)
            hero_goal = rule_data.get("hero_goal", hero_goal)
            traitor_goal = rule_data.get("traitor_goal", traitor_goal)
            monsters = list(rule_data.get("suggested_monsters", monsters))
            notes = rule_data.get("engine_note", notes)
        haunt_defs[haunt_id] = Haunt(
            id=haunt_id,
            name=translation.get("title_zh", name),
            source_name=name,
            traitor_rule=rule,
            hero_goal=hero_goal,
            traitor_goal=traitor_goal,
            hero_script=translation.get("hero", ""),
            traitor_script=translation.get("traitor", ""),
            mode=rule_data.get("mode", "generic"),
            trigger_hint="theme",
            suggested_monsters=monsters,
            notes=notes,
            rule_data=rule_data,
        )

    monsters = {spec["id"]: MonsterTemplate(**spec) for spec in MONSTER_BASES}

    return Catalog(
        characters=characters,
        character_cards=character_cards,
        cards=cards,
        room_templates=room_templates,
        room_draw_pool=room_draw_pool,
        haunt_defs=haunt_defs,
        monsters=monsters,
        start_room_ids=["basement_landing", "entrance_hall", "foyer", "grand_staircase", "upper_landing"],
        room_targets=room_targets,
    )
