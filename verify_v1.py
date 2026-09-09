from __future__ import annotations

import json
import sys
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

# 桌面版依赖 tkinter。很多精简版 Python（含部分官方安装包与虚拟环境）
# 不带 tkinter，直接用会抛 ModuleNotFoundError，看起来像"代码坏了"，
# 实际只是解释器选错了。这里先给出明确指引，避免误判成回归。
try:
    import tkinter  # noqa: F401
except ModuleNotFoundError:
    sys.stderr.write(
        "\n[环境错误] 当前 Python 没有 tkinter，无法运行桌面版测试。\n"
        f"  当前解释器：{sys.executable}\n"
        f"  Python 版本：{sys.version.split()[0]}\n"
        "  请改用带 tkinter 的解释器，例如：\n"
        r"  D:\Various_programming_languages\pycharm\python3.9\python.exe verify_v1.py"
        "\n\n"
    )
    raise SystemExit(2)

if __package__ in {None, ""}:
    package_root = Path(__file__).resolve().parent
    project_root = package_root.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    import game.ui as ui_module
    from game.bot_ai import BotController
    from game.content import build_catalog
    from game.engine import GameEngine
    from game.ui import GameApp
    from game.net.serialize import state_to_dict, state_to_view_dict
else:
    from . import ui as ui_module
    from .bot_ai import BotController
    from .content import build_catalog
    from .engine import GameEngine
    from .ui import GameApp
    from .net.serialize import state_to_dict, state_to_view_dict


# 通用行动/轨道胜负回归样本：须为 fidelity=skeleton、hero_progress target>=2、
# 无 required_cards/无 action requires、且不在当前精修批次队列内的剧本；
# 精修到该号时必须同步把此常量搬迁到另一个仍满足条件的骨架剧本。
_GENERIC_SAMPLE_HAUNT = 69  # 68 号已于 M10-12 精修，骨架样本顺延到 69（h69_hero_task 无 requires、rooms 含 foyer、target=player_count）


def _configs(count: int = 4, bot_difficulty: str = "hard") -> list[dict]:
    probe = GameEngine(seed=7)
    faces = list(probe.catalog.characters)
    configs = [{"name": "玩家1", "character_id": faces[0], "control": "human"}]
    for index in range(1, count):
        configs.append(
            {
                "name": f"机器人{index + 1}",
                "character_id": faces[index],
                "control": "bot",
                "bot_difficulty": bot_difficulty,
                "bot_style": "aggressive" if bot_difficulty == "hard" else "balanced",
            }
        )
    return configs


class _ScriptedPrompter:
    def __init__(self, choices: list[int | None] | None = None, confirms: list[bool] | None = None) -> None:
        self.choices = list(choices or [])
        self.confirms = list(confirms or [])
        self.prompts: list[tuple[str, str]] = []
        self.notifications: list[tuple[str, str]] = []
        self.splits: list[tuple[str, int]] = []

    def notify(self, title: str, message: str) -> None:
        self.notifications.append((title, message))

    def confirm(self, title: str, message: str) -> bool:
        self.prompts.append((title, message))
        return self.confirms.pop(0) if self.confirms else True

    def choose_from_list(self, title: str, message: str, options: list[str]) -> int | None:
        self.prompts.append((title, message))
        return self.choices.pop(0) if self.choices else 0

    def choose_rotation(self, title, message, placements, entry_direction) -> int | None:
        self.prompts.append((title, message))
        return self.choices.pop(0) if self.choices else 0

    def choose_split_damage(self, title, message, amount, first_label, second_label) -> int | None:
        self.splits.append((title, amount))
        return 0


def verify_start_and_bots() -> None:
    engine = GameEngine(seed=7)
    engine.start_new_game(_configs(4, "hard"))
    assert len(engine.state.players) == 4
    assert engine.state.players[1].control == "bot"
    assert engine.state.players[1].bot_difficulty == "hard"
    assert engine.state.phase == "EXPLORE"


def verify_bots_explore_upper_floor() -> None:
    """机器人应主动跨楼层探索，而不是在一层/地下室的楼梯口循环。"""
    engine = GameEngine(seed=17)
    faces = list(engine.catalog.characters)
    engine.start_new_game(
        [
            {
                "name": f"机器人{i + 1}",
                "character_id": faces[i],
                "control": "bot",
                "bot_difficulty": "hard",
                "bot_style": "aggressive",
            }
            for i in range(4)
        ]
    )
    # 这项测试只验证探索路线，避免随机作祟把测试提前切换到另一阶段。
    engine._resolve_haunt_check = lambda player: False  # type: ignore[method-assign]
    controller = BotController()
    for _ in range(64):
        if engine.state.phase == "GAME_OVER":
            break
        assert controller.take_turn(engine)

    upper_rooms = [
        room
        for room in engine.state.board.values()
        if room.floor == 1 and room.template_id != "upper_landing"
    ]
    assert upper_rooms, "机器人没有放置任何二层新房间"
    assert any(room.visit_count > 0 for room in upper_rooms), "机器人没有真正进入二层房间"


def verify_haunt_fallback_when_omens_end() -> None:
    engine = GameEngine(seed=101)
    engine.start_new_game(_configs(4, "normal"))
    engine.state.last_omen_id = next(
        card_id for card_id, card in engine.catalog.cards.items() if card.kind == "omen"
    )
    engine.state.omens_drawn = 7
    engine.state.haunt_pending = True
    engine.state.room_deck.clear()
    engine.state.room_discard.clear()
    for room in engine.state.board.values():
        room.revealed = True
    engine.roll_dice = lambda count, label: 12  # type: ignore[method-assign]

    assert not engine._has_future_omen_source()
    assert engine._resolve_haunt_check(engine.current_player)
    assert engine.state.phase == "HAUNT_PHASE"
    assert engine.state.haunt is not None


def verify_hidden_haunt_state() -> None:
    engine = GameEngine(seed=11)
    faces = list(engine.catalog.characters)
    engine.start_new_game(
        [
            {"name": f"玩家{i + 1}", "character_id": faces[i], "control": "human"}
            for i in range(4)
        ]
    )
    engine.state.last_omen_id = next(
        card_id for card_id, card in engine.catalog.cards.items() if card.kind == "omen"
    )
    engine._trigger_haunt(engine.current_player)

    traitor_id = engine.state.traitor_id
    assert traitor_id is not None
    hero = next(player for player in engine.state.players if player.id != traitor_id)
    traitor = engine.state.players[traitor_id]

    hero_view = state_to_view_dict(engine.state, hero.id)
    traitor_view = state_to_view_dict(engine.state, traitor.id)
    hero_blob = json.dumps(hero_view, ensure_ascii=False)
    traitor_blob = json.dumps(traitor_view, ensure_ascii=False)

    assert hero_view["traitor_id"] is None
    assert hero_view["haunt"]["traitor_goal"] == ""
    assert hero_view["haunt"]["traitor_script"] == ""
    assert engine.state.haunt.traitor_script not in hero_blob
    assert all(player["role"] == "unknown" for player in hero_view["players"] if player["id"] != hero.id)
    assert all(card_id == "__hidden__" for deck in hero_view["card_decks"].values() for card_id in deck)
    assert "【叛徒秘密" not in "\n".join(hero_view["log"])

    assert traitor_view["traitor_id"] == traitor.id
    assert traitor_view["haunt"]["traitor_script"]
    assert traitor_view["haunt"]["hero_script"] == ""
    assert engine.state.haunt.hero_script not in traitor_blob


def verify_ranged_targets() -> None:
    engine = GameEngine(seed=13)
    faces = list(engine.catalog.characters)
    engine.start_new_game(
        [
            {"name": f"玩家{i + 1}", "character_id": faces[i], "control": "human"}
            for i in range(4)
        ]
    )
    attacker = engine.current_player
    target = next(player for player in engine.state.players if player.id != attacker.id)
    target.room_key = "0:1:0"
    attacker.items.append("item_revolver")
    engine.state.phase = "HAUNT_PHASE"
    attacker.role = "hero"
    target.role = "traitor"

    assert target not in engine.available_attack_targets(attacker, ranged=False)
    assert target in engine.available_attack_targets(attacker, ranged=True)


def verify_haunt_rule_catalog() -> None:
    from game.haunt_modes import get_mode_handler, GenericModeHandler

    catalog = build_catalog(17)
    valid_rooms = set(catalog.room_templates)
    valid_monsters = set(catalog.monsters)
    for haunt_id in range(1, 71):
        haunt = catalog.haunt_defs[haunt_id]
        mode = (haunt.rule_data or {}).get("mode", "")
        assert haunt.mode != "generic", haunt_id
        assert haunt.rule_data, haunt_id
        assert haunt.rule_data.get("version", 0) >= 1, haunt_id
        assert haunt.rule_data.get("status") == "playable", haunt_id
        assert haunt.rule_data.get("hero_goal"), haunt_id
        assert haunt.rule_data.get("traitor_goal"), haunt_id
        assert haunt.rule_data.get("setup", {}).get("tracks"), haunt_id
        # 定制 handler 可以把行动做成自动结算（如剧本 10 困僵尸），允许空表；
        # 通用规则的剧本必须有可点的 actions（handler 都继承 GenericModeHandler，
        # 所以用"类型不是基类本身"判断是否定制）
        has_custom_handler = type(get_mode_handler(mode)) is not GenericModeHandler
        assert haunt.rule_data.get("actions") or has_custom_handler, haunt_id
        assert haunt.rule_data.get("win_conditions") or has_custom_handler, haunt_id
        assert set(haunt.rule_data.get("key_rooms", [])) <= valid_rooms, haunt_id
        assert {
            spec.get("template_id")
            for spec in haunt.rule_data.get("monsters", [])
            if spec.get("template_id")
        } <= valid_monsters, haunt_id
        action_ids = [action.get("id") for action in haunt.rule_data.get("actions", [])]
        assert len(action_ids) == len(set(action_ids)), haunt_id
        assert haunt.hero_script
        assert haunt.traitor_script
    for monster_id in ["witch", "cat", "giant_spider", "dog", "alien", "creeper_tip", "banshee", "madman"]:
        assert monster_id in catalog.monsters

    # 70 个剧本不但有规则，还必须在当前选表算法中可达；角色轨道也不能退回旧式上限逻辑。
    selected = {
        GameEngine(seed=haunt_id)._select_haunt_id(f"room_{haunt_id}", f"omen_{haunt_id}")
        for haunt_id in range(500)
    }
    assert selected == set(range(1, 71)), selected
    warren = catalog.characters["card_5_1"]
    assert warren.stats_tracks
    assert warren.stats_tracks["sanity"][-1] == 8
    assert warren.stats_tracks["knowledge"][-1] == 8


def verify_supplemental_rooms_and_events() -> None:
    catalog = build_catalog(31)
    supplemental_rooms = {
        "attic": "room_attic",
        "bathroom": "room_bathroom",
        "game_room": "room_game_room",
        "inner_hall": "room_inner_hall",
        "creaky_hallway": "room_creaky_hallway",
        "dusty_hallway": "room_dusty_hallway",
        "statuary_corridor": "room_statuary_corridor",
        "crawlspace": "room_crawlspace",
        "underground_lake": "room_underground_lake",
        "wine_cellar": "room_wine_cellar",
    }
    assert {catalog.room_templates[key].effect_id for key in supplemental_rooms} == set(supplemental_rooms.values())
    assert all(not room.generated for room in catalog.room_templates.values())

    event_cards = [
        card for card in catalog.cards.values()
        if card.kind == "event" and card.id in {
            "event_awful_waffles", "event_smoke", "event_whoops", "event_disquieting_sounds",
            "event_spider", "event_closet_door", "event_locked_safe", "event_groundskeeper",
            "event_something_slimy", "event_a_moment_of_hope", "event_hanged_men",
            "event_jonahs_turn", "event_it_is_meant_to_be", "event_something_hidden",
            "event_the_voice", "event_webs", "event_night_view", "event_creepy_crawlies",
            "event_phone_call",
        }
    ]
    assert len(event_cards) == 19
    assert all(card.effect_id != "event_generic" for card in event_cards)
    assert len({card.effect_id for card in event_cards}) == 19

    # 每个新增事件都至少走一遍真实解析分支，避免只替换 effect_id 而按钮/抽牌后无响应。
    for card in event_cards:
        engine = GameEngine(seed=37)
        engine.start_new_game(_configs(4, "normal"))
        engine.prompter = _ScriptedPrompter(choices=[0], confirms=[True])
        engine._resolve_check = lambda player, stat, target, label: True  # type: ignore[method-assign]
        engine._resolve_event(engine.current_player, card)

    # 地下湖的特殊行为单独验证；普通补充房间则应有明确的无基础特效分支。
    engine = GameEngine(seed=41)
    engine.start_new_game(_configs(4, "normal"))
    player = engine.current_player
    lake = engine._place_room(catalog.room_templates["underground_lake"], 10, 10, 0)
    player.room_key = lake.key
    lake.floor = 1
    engine._apply_room_effect(player, lake, first_entry=True)
    assert lake.data.get("collapsed") is True
    assert player.movement_stopped is True


def verify_generic_haunt_action_and_victory() -> None:
    # 用仍是模板骨架的 _GENERIC_SAMPLE_HAUNT 号剧本验证通用行动/轨道胜负
    # （它是全库唯一验证“骨架剧本通用行动 + 轨道多次累加至 target 触发胜利”的回归网；
    #   已精修剧本见 verify_haunt_systems 的对应专属用例）
    sample = _GENERIC_SAMPLE_HAUNT
    hero_task = f"h{sample}_hero_task"
    engine = GameEngine(seed=43)
    engine.start_new_game(_configs(4, "normal"))
    _trigger_specific_haunt(engine, sample)
    hero = next(player for player in engine.state.players if player.role == "hero")
    # 该骨架剧本声明的房间列表里有保险库，用它做落房
    room_key = _place_test_room(engine, "foyer", 66, 0)
    hero.room_key = room_key
    engine.state.turn_order = [hero.id]
    engine.state.turn_index = 0
    engine._resolve_check = lambda player, stat, target, label: True  # type: ignore[method-assign]
    actions = engine.available_haunt_actions(hero)
    assert any(action.id == hero_task for action in actions)
    assert engine.perform_haunt_action(hero, hero_task)
    assert engine.state.meta["haunt_rule"]["tracks"]["hero_progress"]["value"] == 1

    # 循环次数按该剧本骨架声明的轨道目标值驱动（sample=48 时 target=2，多回合累加）；
    # 目标为 1 的剧本在首次行动时即获胜，循环自然跳过
    track = engine.state.meta["haunt_rule"]["tracks"]["hero_progress"]
    loops = 0
    while track["value"] < track["target"] and engine.state.phase == "HAUNT_PHASE":
        engine._reset_player_turn_state(hero)
        assert engine.perform_haunt_action(hero, hero_task)
        loops += 1
    assert track["value"] == track["target"]
    assert engine.state.winner == "heroes"


def verify_haunt_rule_init_and_privacy() -> None:
    engine = GameEngine(seed=19)
    engine.start_new_game(_configs(6, "normal"))
    engine.state.last_omen_id = next(
        card_id for card_id, card in engine.catalog.cards.items() if card.kind == "omen"
    )
    engine._select_haunt_id = lambda room_id, omen_id: 6  # type: ignore[method-assign]
    engine._trigger_haunt(engine.current_player)

    rule_state = engine.state.meta.get("haunt_rule", {})
    assert rule_state["id"] == 6
    assert rule_state["tracks"]["spaceship_damage"]["target"] == 6
    aliens = [monster for monster in engine.state.monsters if monster.template_id == "alien"]
    assert len(aliens) == 2
    assert all(monster.might == 6 and monster.sanity == 6 for monster in aliens)

    hero = next(player for player in engine.state.players if player.role == "hero")
    hero_view = state_to_view_dict(engine.state, hero.id)
    assert hero_view["haunt"]["rule_data"] == {}
    assert "haunt_rule" not in hero_view["meta"]


def _trigger_specific_haunt(engine: GameEngine, haunt_id: int) -> None:
    engine.state.last_omen_id = next(
        card_id for card_id, card in engine.catalog.cards.items() if card.kind == "omen"
    )
    engine._select_haunt_id = lambda room_id, omen_id: haunt_id  # type: ignore[method-assign]
    engine._trigger_haunt(engine.current_player)


def _place_test_room(engine: GameEngine, room_id: str, x: int = 8, y: int = 0) -> str:
    template = engine.catalog.room_templates[room_id]
    room = engine._place_room(template, x, y, 0)
    return room.key


def _force_ui_human_turn(app: GameApp, player_id: int = 0) -> None:
    state = app.engine.state
    state.turn_order = [player_id]
    state.turn_index = 0
    state.players[player_id].control = "human"
    state.players[player_id].dead = False
    state.players[player_id].steps_remaining = max(1, state.players[player_id].steps_remaining)
    state.players[player_id].movement_stopped = False


def verify_haunt1_actions_and_victory() -> None:
    engine = GameEngine(seed=23)
    engine.start_new_game(_configs(4, "normal"))
    _trigger_specific_haunt(engine, 1)
    hero = next(player for player in engine.state.players if player.role == "hero")
    engine._resolve_check = lambda player, stat, target, label: True  # type: ignore[method-assign]
    engine._roll_attack = lambda player, attr, bonus=0: 10  # type: ignore[method-assign]
    engine._roll_monster_attack = lambda monster, attr, reroll_blanks=False: 0  # type: ignore[method-assign]

    library_key = _place_test_room(engine, "library")
    hero.room_key = library_key
    hero.items.append("omen_book")

    actions = engine.available_haunt_actions(hero)
    assert any(action.id == "h1_learn_true_name" for action in actions)
    assert engine.perform_haunt_action(hero, "h1_learn_true_name")
    assert engine.state.meta["haunt_rule"]["tracks"]["banishment_steps"]["value"] == 1

    engine._reset_player_turn_state(hero)
    assert engine.perform_haunt_action(hero, "h1_learn_spell")
    assert engine.state.meta["haunt_rule"]["tracks"]["banishment_steps"]["value"] == 2

    mummy = next(monster for monster in engine.state.monsters if monster.template_id == "mummy")
    hero.room_key = mummy.room_key
    engine._reset_player_turn_state(hero)
    assert engine.perform_haunt_action(hero, "h1_banish_mummy")
    assert engine.state.winner == "heroes"


def verify_haunt5_silver_bullet_kill() -> None:
    engine = GameEngine(seed=29)
    engine.start_new_game(_configs(4, "normal"))
    _trigger_specific_haunt(engine, 5)
    hero = next(player for player in engine.state.players if player.role == "hero")
    traitor = next(player for player in engine.state.players if player.role == "traitor")
    engine._resolve_check = lambda player, stat, target, label: True  # type: ignore[method-assign]
    engine._roll_attack = lambda player, attr, bonus=0: 10 if player.id == hero.id else 0  # type: ignore[method-assign]

    game_room_key = _place_test_room(engine, "game_room", 9, 0)
    hero.room_key = game_room_key
    assert engine.perform_haunt_action(hero, "h5_find_revolver")
    assert "item_revolver" in hero.items

    engine._reset_player_turn_state(hero)
    lab_key = _place_test_room(engine, "research_laboratory", 10, 0)
    hero.room_key = lab_key
    assert engine.perform_haunt_action(hero, "h5_make_silver_bullets")
    assert engine.state.meta["haunt_rule"]["flags"]["silver_bullets_holder"] == hero.id

    engine._reset_player_turn_state(hero)
    traitor.room_key = hero.room_key
    assert engine.attack(hero, traitor, "item_revolver", ranged=True)
    assert traitor.dead
    assert engine.state.winner == "heroes"


def verify_haunt5_infection_conversion() -> None:
    engine = GameEngine(seed=31)
    engine.start_new_game(_configs(4, "normal"))
    _trigger_specific_haunt(engine, 5)
    hero = next(player for player in engine.state.players if player.role == "hero")
    dog = next(monster for monster in engine.state.monsters if monster.template_id == "dog")
    dog.room_key = hero.room_key
    engine._roll_monster_attack = lambda monster, attr, reroll_blanks=False: 1  # type: ignore[method-assign]
    engine._roll_attack = lambda player, attr, bonus=0: 0  # type: ignore[method-assign]
    engine._monster_attack(dog, hero)
    assert hero.id in engine.state.meta["haunt_rule"]["flags"]["infected"]

    engine._resolve_check = lambda player, stat, target, label: False  # type: ignore[method-assign]
    engine._apply_start_of_turn_haunt_effects(hero)
    assert hero.role == "traitor"


def verify_save_load_roundtrip() -> None:
    engine = GameEngine(seed=41)
    engine.start_new_game(_configs(4, "normal"))
    player = engine.state.players[0]
    item_id = next(card_id for card_id, card in engine.catalog.cards.items() if card.kind == "item")
    player.items.append(item_id)
    engine.state.room_items.setdefault(player.room_key, []).append(item_id)
    engine.state.log.append("测试存档日志")
    engine._next_monster_id = 99
    before = state_to_dict(engine.state)
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "local_save.json"
        engine.save_to_file(path)
        expected_roll = engine.rng.randint(1, 1000000)
        loaded = GameEngine(seed=99)
        loaded.load_from_file(path)
        assert state_to_dict(loaded.state) == before
        assert loaded._next_monster_id == 99
        assert loaded.rng.randint(1, 1000000) == expected_roll


def verify_ui_button_layout() -> None:
    app = GameApp()
    try:
        app.update()
        assert hasattr(app, "btn_local_start")
        assert app.btn_save.winfo_width() >= 45
        assert app.btn_load.winfo_width() >= 45
        assert app.btn_save["state"] == "disabled"
        assert app.btn_load["state"] == "normal"
        root_x = app.winfo_rootx()
        root_y = app.winfo_rooty()
        root_w = app.winfo_width()
        root_h = app.winfo_height()
        start_x = app.btn_local_start.winfo_rootx()
        start_y = app.btn_local_start.winfo_rooty()
        assert app.btn_local_start.winfo_width() >= 90
        assert app.btn_local_start.winfo_height() >= 36
        assert root_x <= start_x < root_x + root_w
        assert root_y <= start_y < root_y + root_h
        assert start_x + app.btn_local_start.winfo_width() <= root_x + root_w
        assert start_y + app.btn_local_start.winfo_height() <= root_y + root_h

        app._begin_game_from_form()
        app.update()
        buttons = [
            app.btn_move,
            app.btn_use,
            app.btn_haunt_action,
            app.btn_pickup,
            app.btn_drop,
            app.btn_trade,
            app.btn_attack,
            app.btn_script,
            app.btn_end,
            app.btn_save,
            app.btn_load,
        ]
        action_buttons = buttons[:-2]
        assert all(button.winfo_width() >= 90 and button.winfo_height() >= 45 for button in action_buttons)
        assert app.btn_save["state"] == "normal"
        assert app.btn_load["state"] == "normal"
        assert hasattr(app, "action_hint")
        assert hasattr(app, "btn_zoom_in")
        assert hasattr(app, "btn_zoom_out")
        assert hasattr(app, "btn_inspect_players")
        assert hasattr(app, "main_splitter")
        assert app.board_hscroll.winfo_ismapped()
        assert app.right_scroll.winfo_ismapped()
        assert app.log_hscroll.winfo_ismapped()
        right_bbox = app.right_canvas.bbox("all")
        assert right_bbox is not None and right_bbox[3] > app.right_canvas.winfo_height()
    finally:
        app.destroy()


def verify_direct_room_click() -> None:
    app = GameApp()
    messages: list[tuple[str, str]] = []
    try:
        app.update()
        app._show_info = lambda title, message: messages.append((title, message))  # type: ignore[method-assign]
        app._begin_game_from_form()
        app.update()
        # 房间进入效果会通过 DecisionProvider 弹窗；回归测试不能等待真实人工窗口。
        app.engine.prompter = _ScriptedPrompter()
        _force_ui_human_turn(app, 0)
        player = app.engine.current_player
        player.steps_remaining = 1
        player.movement_stopped = False
        target_key = "0:1:0"  # 初始门厅，与入口大厅通过东/西门相连
        app._on_room_click(target_key)
        assert player.room_key == target_key

        player.steps_remaining = 0
        player.movement_stopped = False
        app._on_room_click("0:0:0")
        assert player.room_key == target_key
        assert messages
    finally:
        app.destroy()


def verify_exploration_slots() -> None:
    app = GameApp()
    messages: list[tuple[str, str]] = []
    try:
        app.update()
        app._show_info = lambda title, message: messages.append((title, message))  # type: ignore[method-assign]
        app._begin_game_from_form()
        app.update()
        _force_ui_human_turn(app, 0)
        player = app.engine.current_player
        player.steps_remaining = max(1, player.steps_remaining)
        player.movement_stopped = False
        app._redraw_board()
        app.update()
        assert app._exploration_slots, "当前有合法探索门位，但地图没有绘制白色方格"
        slot_tag, slot = next(iter(app._exploration_slots.items()))
        rect = slot["rect"]
        assert app.board_canvas.type(rect) == "rectangle"
        app._on_exploration_slot_enter(slot_tag)
        assert app.board_canvas.itemcget(rect, "outline") == "#ffffff"
        app._on_exploration_slot_leave(slot_tag)
        assert app.board_canvas.itemcget(rect, "outline") == "#b9c4d1"

        app.engine.prompter = _ScriptedPrompter(choices=[0])
        app._on_exploration_slot_click(slot_tag)
        assert len(app.engine.state.board) > len(app.engine.catalog.start_room_ids)
        assert not app._exploration_slots or player.room_key in app.engine.state.board

        player.steps_remaining = 0
        player.movement_stopped = False
        app._redraw_board()
        assert not app._exploration_slots
    finally:
        app.destroy()


def verify_ui_buttons_have_responses() -> None:
    app = GameApp()
    info_messages: list[tuple[str, str]] = []
    text_dialogs: list[tuple[str, str]] = []
    try:
        app.update()
        app._show_info = lambda title, message: info_messages.append((title, message))  # type: ignore[method-assign]
        app._show_error = lambda title, message: info_messages.append((title, message))  # type: ignore[method-assign]
        assert app.btn_local_start["command"]
        app.btn_local_start.invoke()
        app.update()
        assert app.engine.state.players
        _force_ui_human_turn(app, 0)

        visible_buttons = [
            app.btn_move,
            app.btn_use,
            app.btn_pickup,
            app.btn_drop,
            app.btn_trade,
            app.btn_attack,
            app.btn_haunt_action,
            app.btn_script,
            app.btn_end,
            app.btn_save,
            app.btn_load,
            app.btn_zoom_in,
            app.btn_zoom_out,
            app.btn_inspect_players,
        ]
        for button in visible_buttons:
            assert button.winfo_ismapped(), button["text"]
            assert button["command"], button["text"]
            assert button.winfo_width() >= 20, button["text"]
            assert button.winfo_height() >= 20, button["text"]

        with TemporaryDirectory() as tmp:
            save_path = Path(tmp) / "ui_save.json"
            app.engine.prompter = _ScriptedPrompter(confirms=[True])
            with patch.object(ui_module.filedialog, "asksaveasfilename", return_value=str(save_path)):
                app.btn_save.invoke()
            assert save_path.exists()
            app.engine.state.log.append("读取前的临时改动")
            with patch.object(ui_module.filedialog, "askopenfilename", return_value=str(save_path)):
                app.btn_load.invoke()
            assert "读取前的临时改动" not in app.engine.state.log
            assert any(title == "读取成功" for title, _ in info_messages)

        player = app.engine.current_player
        _force_ui_human_turn(app, player.id)
        app.engine.prompter = _ScriptedPrompter(choices=[None])
        app._refresh_ui()
        if app.btn_move["state"] == "normal":
            prompts_before = len(app.engine.prompter.prompts)
            app.btn_move.invoke()
            assert len(app.engine.prompter.prompts) > prompts_before

        app.engine.prompter = _ScriptedPrompter()
        _force_ui_human_turn(app, 0)
        player = app.engine.current_player
        player.items.append("item_adrenaline_shot")
        player.item_used = False
        steps_before = player.steps_remaining
        app._refresh_ui()
        assert app.btn_use["state"] == "normal"
        app.btn_use.invoke()
        assert player.steps_remaining > steps_before

        player = app.engine.current_player
        _force_ui_human_turn(app, player.id)
        pickup_card = "item_puzzle_box"
        if pickup_card in player.items:
            player.items.remove(pickup_card)
        app.engine.state.room_items.setdefault(player.room_key, []).append(pickup_card)
        app.engine.prompter = _ScriptedPrompter(choices=[0])
        app._refresh_ui()
        assert app.btn_pickup["state"] == "normal"
        app.btn_pickup.invoke()
        assert pickup_card in player.items

        app.engine.prompter = _ScriptedPrompter(choices=[player.items.index(pickup_card)])
        _force_ui_human_turn(app, player.id)
        app._refresh_ui()
        assert app.btn_drop["state"] == "normal"
        app.btn_drop.invoke()
        assert pickup_card not in player.items
        assert pickup_card in app.engine.room_items(player.room_key)

        trade_card = "item_bottle"
        if trade_card not in player.items:
            player.items.append(trade_card)
        target = app.engine.state.players[1]
        target.room_key = player.room_key
        target.control = "human"
        if trade_card in target.items:
            target.items.remove(trade_card)
        app.engine.prompter = _ScriptedPrompter(choices=[0, player.items.index(trade_card)])
        _force_ui_human_turn(app, player.id)
        app._refresh_ui()
        assert app.btn_trade["state"] == "normal"
        app.btn_trade.invoke()
        assert trade_card in target.items

        app.engine.state.phase = "HAUNT_PHASE"
        player.role = "hero"
        target.role = "traitor"
        target.room_key = player.room_key
        player.attack_used = False
        app.engine.prompter = _ScriptedPrompter(choices=[0], confirms=[False])
        _force_ui_human_turn(app, player.id)
        app._refresh_ui()
        assert app.btn_attack["state"] == "normal"
        app.btn_attack.invoke()
        assert player.attack_used is True

        _trigger_specific_haunt(app.engine, 5)
        hero = next(p for p in app.engine.state.players if p.role == "hero")
        game_room_key = _place_test_room(app.engine, "game_room", 11, 0)
        hero.room_key = game_room_key
        for owner in app.engine.state.players:
            while "item_revolver" in owner.items:
                owner.items.remove("item_revolver")
            while "item_revolver" in owner.companions:
                owner.companions.remove("item_revolver")
        for room_cards in app.engine.state.room_items.values():
            while "item_revolver" in room_cards:
                room_cards.remove("item_revolver")
        _force_ui_human_turn(app, hero.id)
        hero.attack_used = False
        app.engine._resolve_check = lambda player, stat, target, label: True  # type: ignore[method-assign]
        app.engine.prompter = _ScriptedPrompter(choices=[0], confirms=[True])
        app._refresh_ui()
        assert app.btn_haunt_action["state"] == "normal"
        app.btn_haunt_action.invoke()
        assert "item_revolver" in hero.items

        class _FakeTextDialog:
            def __init__(self, root, title, text) -> None:
                text_dialogs.append((title, text))
                self.top = None

        app.wait_window = lambda _top: None  # type: ignore[method-assign]
        with patch.object(ui_module, "_TextDialog", _FakeTextDialog):
            app._refresh_ui()
            assert app.btn_script["state"] == "normal"
            app.btn_script.invoke()
        assert text_dialogs

        before_zoom = app.zoom
        app.btn_zoom_in.invoke()
        assert app.zoom > before_zoom
        app.btn_zoom_out.invoke()
        assert app.zoom <= before_zoom + 0.01

        app.engine.prompter = _ScriptedPrompter(choices=[0])
        app.btn_inspect_players.invoke()
        assert app.engine.prompter.prompts[-1][0] == "查看玩家"

        before_turn = app.engine.state.turn_count
        app._refresh_ui()
        assert app.btn_end["state"] == "normal"
        app.btn_end.invoke()
        assert app.engine.state.turn_count >= before_turn
    finally:
        app.destroy()


def main() -> None:
    verify_start_and_bots()
    verify_bots_explore_upper_floor()
    verify_haunt_fallback_when_omens_end()
    verify_hidden_haunt_state()
    verify_ranged_targets()
    verify_haunt_rule_catalog()
    verify_supplemental_rooms_and_events()
    verify_generic_haunt_action_and_victory()
    verify_haunt_rule_init_and_privacy()
    verify_haunt1_actions_and_victory()
    verify_haunt5_silver_bullet_kill()
    verify_haunt5_infection_conversion()
    verify_save_load_roundtrip()
    verify_ui_button_layout()
    verify_direct_room_click()
    verify_exploration_slots()
    verify_ui_buttons_have_responses()
    print("verify_v1: ok")


if __name__ == "__main__":
    main()
