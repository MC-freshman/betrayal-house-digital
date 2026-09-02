"""GameState 及其数据类的序列化（服务器 → 客户端，JSON 安全 dict）。

联机时必须按接收者裁剪状态，避免叛徒手册、叛徒身份和牌堆顺序泄漏。
"""
from __future__ import annotations

try:
    from ..models import GameState, Haunt, Monster, PlacedRoom, Player, Token
except ImportError:  # pragma: no cover - direct script execution
    from models import GameState, Haunt, Monster, PlacedRoom, Player, Token


# ---------------------------------------------------------------- Player
def player_to_dict(p: Player) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "character_id": p.character_id,
        "character_name": p.character_name,
        "source_name": p.source_name,
        "aliases": list(p.aliases),
        "birthday": p.birthday,
        "stats": dict(p.stats),
        "stats_max": dict(p.stats_max),
        "stats_tracks": {k: list(v) for k, v in p.stats_tracks.items()},
        "stat_positions": dict(p.stat_positions),
        "overflow": dict(p.overflow),
        "room_key": p.room_key,
        "items": list(p.items),
        "companions": list(p.companions),
        "role": p.role,
        "dead": p.dead,
        "steps_remaining": p.steps_remaining,
        "attack_used": p.attack_used,
        "item_used": p.item_used,
        "moved_this_turn": p.moved_this_turn,
        "movement_stopped": p.movement_stopped,
        "extra_speed_this_turn": p.extra_speed_this_turn,
        "extra_check_rerolls": p.extra_check_rerolls,
        "ignore_first_physical_damage": p.ignore_first_physical_damage,
        "next_check_auto_success": p.next_check_auto_success,
        "saved_roll": p.saved_roll,
        "notes": list(p.notes),
        "control": p.control,
        "bot_difficulty": p.bot_difficulty,
        "bot_style": p.bot_style,
    }


def player_to_view_dict(p: Player, viewer_id: int | None, phase: str, game_over: bool = False) -> dict:
    data = player_to_dict(p)
    is_self = viewer_id is not None and p.id == viewer_id
    if phase == "HAUNT_PHASE" and not game_over and not is_self:
        data["role"] = "unknown"
    if not is_self:
        data["notes"] = []
    return data


def player_from_dict(d: dict) -> Player:
    return Player(
        id=d["id"],
        name=d["name"],
        character_id=d.get("character_id", ""),
        character_name=d.get("character_name", ""),
        source_name=d.get("source_name", ""),
        aliases=list(d.get("aliases", [])),
        birthday=d.get("birthday", ""),
        stats=dict(d.get("stats", {})),
        stats_max=dict(d.get("stats_max", {})),
        stats_tracks={k: list(v) for k, v in d.get("stats_tracks", {}).items()},
        stat_positions={k: int(v) for k, v in d.get("stat_positions", {}).items()},
        overflow={k: int(v) for k, v in d.get("overflow", {}).items()},
        room_key=d.get("room_key", ""),
        items=list(d.get("items", [])),
        companions=list(d.get("companions", [])),
        role=d.get("role", "explorer"),
        dead=d.get("dead", False),
        steps_remaining=d.get("steps_remaining", 0),
        attack_used=d.get("attack_used", False),
        item_used=d.get("item_used", False),
        moved_this_turn=d.get("moved_this_turn", False),
        movement_stopped=d.get("movement_stopped", False),
        extra_speed_this_turn=d.get("extra_speed_this_turn", 0),
        extra_check_rerolls=d.get("extra_check_rerolls", 0),
        ignore_first_physical_damage=d.get("ignore_first_physical_damage", False),
        next_check_auto_success=d.get("next_check_auto_success", False),
        saved_roll=d.get("saved_roll"),
        notes=list(d.get("notes", [])),
        control=d.get("control", "human"),
        bot_difficulty=d.get("bot_difficulty", "normal"),
        bot_style=d.get("bot_style", "balanced"),
    )


# ---------------------------------------------------------------- PlacedRoom
def room_to_dict(r: PlacedRoom) -> dict:
    return {
        "key": r.key,
        "template_id": r.template_id,
        "name": r.name,
        "floor": r.floor,
        "x": r.x,
        "y": r.y,
        "rotation": r.rotation,
        "doors": list(r.doors),
        "symbol": r.symbol,
        "effect_id": r.effect_id,
        "text": r.text,
        "special": r.special,
        "links": dict(r.links),
        "discovered_by": r.discovered_by,
        "revealed": r.revealed,
        "first_effect_done": r.first_effect_done,
        "visit_count": r.visit_count,
        "data": dict(r.data),
    }


def room_from_dict(d: dict) -> PlacedRoom:
    return PlacedRoom(
        key=d["key"],
        template_id=d.get("template_id", ""),
        name=d.get("name", ""),
        floor=d.get("floor", 0),
        x=d.get("x", 0),
        y=d.get("y", 0),
        rotation=d.get("rotation", 0),
        doors=tuple(d.get("doors", [])),
        symbol=d.get("symbol"),
        effect_id=d.get("effect_id", "none"),
        text=d.get("text", ""),
        special=d.get("special", False),
        links=dict(d.get("links", {})),
        discovered_by=d.get("discovered_by"),
        revealed=d.get("revealed", False),
        first_effect_done=d.get("first_effect_done", False),
        visit_count=d.get("visit_count", 0),
        data=dict(d.get("data", {})),
    )


# ---------------------------------------------------------------- Monster
def monster_to_dict(m: Monster) -> dict:
    return {
        "id": m.id,
        "template_id": m.template_id,
        "name": m.name,
        "speed": m.speed,
        "might": m.might,
        "sanity": m.sanity,
        "knowledge": m.knowledge,
        "room_key": m.room_key,
        "controller": m.controller,
        "stunned_turns": m.stunned_turns,
        "can_carry_items": m.can_carry_items,
        "items": list(m.items),
        "tags": list(m.tags),
    }


def monster_from_dict(d: dict) -> Monster:
    return Monster(
        id=d["id"],
        template_id=d.get("template_id", ""),
        name=d.get("name", ""),
        speed=d.get("speed", 2),
        might=d.get("might", 2),
        sanity=d.get("sanity", 0),
        knowledge=d.get("knowledge", 0),
        room_key=d.get("room_key", ""),
        controller=d.get("controller", "traitor"),
        stunned_turns=d.get("stunned_turns", 0),
        can_carry_items=d.get("can_carry_items", False),
        items=list(d.get("items", [])),
        tags=tuple(d.get("tags", [])),
    )


# ---------------------------------------------------------------- Token
def token_to_dict(t: Token) -> dict:
    return {
        "uid": t.uid,
        "kind": t.kind,
        "label": t.label,
        "role": t.role,
        "room_key": t.room_key,
        "holder": t.holder,
        "face_up": t.face_up,
        "data": dict(t.data),
    }


def token_from_dict(d: dict) -> Token:
    return Token(
        uid=d.get("uid", ""),
        kind=d.get("kind", ""),
        label=d.get("label", ""),
        role=d.get("role", "marker"),
        room_key=d.get("room_key", ""),
        holder=d.get("holder"),
        face_up=d.get("face_up", True),
        data=dict(d.get("data", {})),
    )


# ---------------------------------------------------------------- Haunt
def haunt_to_dict(h: Haunt | None) -> dict | None:
    if h is None:
        return None
    return {
        "id": h.id,
        "name": h.name,
        "source_name": h.source_name,
        "traitor_rule": h.traitor_rule,
        "hero_goal": h.hero_goal,
        "traitor_goal": h.traitor_goal,
        "hero_script": h.hero_script,
        "traitor_script": h.traitor_script,
        "mode": h.mode,
        "trigger_hint": h.trigger_hint,
        "suggested_monsters": list(h.suggested_monsters),
        "notes": h.notes,
        "rule_data": dict(h.rule_data),
    }


def haunt_to_view_dict(h: Haunt | None, viewer_role: str, game_over: bool = False) -> dict | None:
    data = haunt_to_dict(h)
    if data is None:
        return None
    if game_over:
        data["rule_data"] = {}
        return data
    data["traitor_rule"] = ""
    data["rule_data"] = {}
    if viewer_role == "traitor":
        data["hero_goal"] = ""
        data["hero_script"] = ""
    elif viewer_role == "hero":
        data["traitor_goal"] = ""
        data["traitor_script"] = ""
    else:
        data["hero_goal"] = ""
        data["traitor_goal"] = ""
        data["hero_script"] = ""
        data["traitor_script"] = ""
    return data


def haunt_from_dict(d: dict | None) -> Haunt | None:
    if not d:
        return None
    return Haunt(
        id=d["id"],
        name=d.get("name", ""),
        source_name=d.get("source_name", ""),
        traitor_rule=d.get("traitor_rule", "revealer"),
        hero_goal=d.get("hero_goal", ""),
        traitor_goal=d.get("traitor_goal", ""),
        hero_script=d.get("hero_script", ""),
        traitor_script=d.get("traitor_script", ""),
        mode=d.get("mode", "generic"),
        trigger_hint=d.get("trigger_hint", ""),
        suggested_monsters=list(d.get("suggested_monsters", [])),
        notes=d.get("notes", ""),
        rule_data=dict(d.get("rule_data", {})),
    )


# ---------------------------------------------------------------- GameState
def state_to_dict(s: GameState) -> dict:
    return {
        "phase": s.phase,
        "turn_index": s.turn_index,
        "turn_order": list(s.turn_order),
        "turn_count": s.turn_count,
        "players": [player_to_dict(p) for p in s.players],
        "board": {k: room_to_dict(r) for k, r in s.board.items()},
        "room_deck": list(s.room_deck),
        "room_discard": list(s.room_discard),
        "card_decks": {k: list(v) for k, v in s.card_decks.items()},
        "card_discards": {k: list(v) for k, v in s.card_discards.items()},
        "omens_drawn": s.omens_drawn,
        "last_omen_id": s.last_omen_id,
        "haunt_pending": s.haunt_pending,
        "haunt_revealer_id": s.haunt_revealer_id,
        "haunt": haunt_to_dict(s.haunt),
        "traitor_id": s.traitor_id,
        "monsters": [monster_to_dict(m) for m in s.monsters],
        "tokens": [token_to_dict(t) for t in s.tokens],
        "room_items": {k: list(v) for k, v in s.room_items.items()},
        "log": list(s.log),
        "winner": s.winner,
        "winner_reason": s.winner_reason,
        "seed": s.seed,
        "meta": dict(s.meta),
    }


def state_to_view_dict(s: GameState, viewer_id: int | None) -> dict:
    """返回某个玩家可见的状态。

    客户端只需要牌堆数量，不需要知道具体顺序；其他玩家的阵营和备注也不能泄漏。
    """
    viewer = s.players[viewer_id] if viewer_id is not None and 0 <= viewer_id < len(s.players) else None
    viewer_role = viewer.role if viewer else ""
    game_over = s.phase == "GAME_OVER" or bool(s.winner)
    data = state_to_dict(s)
    data["players"] = [
        player_to_view_dict(player, viewer_id, s.phase, game_over)
        for player in s.players
    ]
    data["card_decks"] = {
        kind: ["__hidden__"] * len(cards)
        for kind, cards in s.card_decks.items()
    }
    data["traitor_id"] = s.traitor_id if game_over or viewer_role == "traitor" else None
    data["haunt"] = haunt_to_view_dict(s.haunt, viewer_role, game_over)
    data["log"] = _public_log_for_viewer(s.log, viewer_role, game_over)
    data["meta"] = {
        "viewer_id": viewer_id,
        "viewer_role": viewer_role if viewer else "",
        "privacy_view": True,
    }
    return data


def _public_log_for_viewer(log: list[str], viewer_role: str, game_over: bool) -> list[str]:
    if game_over:
        return list(log)
    blocked = ("【叛徒秘密", "叛徒秘密", "traitor secret")
    result: list[str] = []
    for line in log:
        if any(token in line for token in blocked):
            if viewer_role == "traitor":
                continue
            continue
        result.append(line)
    return result


def state_from_dict(d: dict) -> GameState:
    s = GameState(
        phase=d.get("phase", "SETUP"),
        turn_index=d.get("turn_index", 0),
        turn_order=list(d.get("turn_order", [])),
        turn_count=d.get("turn_count", 0),
        players=[player_from_dict(p) for p in d.get("players", [])],
        board={k: room_from_dict(v) for k, v in d.get("board", {}).items()},
        pos_index={},
        room_deck=list(d.get("room_deck", [])),
        room_discard=list(d.get("room_discard", [])),
        card_decks={k: list(v) for k, v in d.get("card_decks", {}).items()},
        card_discards={k: list(v) for k, v in d.get("card_discards", {}).items()},
        omens_drawn=d.get("omens_drawn", 0),
        last_omen_id=d.get("last_omen_id"),
        haunt_pending=d.get("haunt_pending", False),
        haunt_revealer_id=d.get("haunt_revealer_id"),
        haunt=haunt_from_dict(d.get("haunt")),
        traitor_id=d.get("traitor_id"),
        monsters=[monster_from_dict(m) for m in d.get("monsters", [])],
        tokens=[token_from_dict(t) for t in d.get("tokens", [])],
        room_items={k: list(v) for k, v in d.get("room_items", {}).items()},
        log=list(d.get("log", [])),
        winner=d.get("winner"),
        winner_reason=d.get("winner_reason", ""),
        seed=d.get("seed"),
        meta=dict(d.get("meta", {})),
    )
    # 重建 pos_index（由 board 派生）
    for key, room in s.board.items():
        s.pos_index[(room.floor, room.x, room.y)] = key
    return s
