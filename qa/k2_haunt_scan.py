#!/usr/bin/env python
"""K2 障碍房（Vault / Tower / Chasm / Catacombs）受影响剧本扫描。

用途：T-06 的机读证据。**只读**：不导入引擎、不改任何规则数据。

判据（写进 docs/K2受影响剧本.md 开头，与本文档同口径）：

* 数据层 = ``haunt_rules.get_haunt_rule_override(n)`` 返回的规则字典（70 本全有）；
  代码层 = ``haunts/haunt_XX_*.py`` 的模块源码文本。
* 「引用」= 该剧本的规则字典里任一字符串值等于四房 id 之一，或 handler 源码里
  出现该 id 的字符串字面量。
* 「胜利必需房」：
  - ``win_conditions`` 里出现该房间 → **是**；
  - 房间出现在「结束对局的那个行动」的 ``rooms`` 里 → **是**；#32 的线索只是加值、终局是
    ``play_organ``（organ_room），故不算；
  - 房间只出现在 ``key_rooms``、前置搜寻/生成、非终局 ``actions.rooms``、``tracks`` 标签或
    handler 常量里 → **间接**。

下面两张表是本脚本唯一的人工判定输入，逐本对过 handler 的 ``check_victory``：

* ``TERMINAL_ACTIONS``：终局动作。只有 #43 的 ``ritual_roll`` 把 tower 列在自己 rooms 里
  （``RITUAL_ROOMS`` 含 tower，且 5–6 人局 need=5 必须把 5 间全用一遍）。
* ``HANDLER_REQUIRED``：数据层没有声明、但 handler 把房间写死为胜利前置。#34 的
  ``lock_up`` 只在保险库可用且库门必须已开（``haunt_34_mad_world.py`` L250 / L271）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent.parent
PHOTOS_ROOMS = ("vault", "tower", "chasm", "catacombs")
OUT_PATH = Path(__file__).resolve().parent / "k2_haunt_scan.json"

# 终局动作（handler check_victory 直接以它推进的轨道/旗标判胜负）
TERMINAL_ACTIONS = {
    43: ("ritual_roll",),   # 仪式令牌数 = min(玩家数, 5)，ritual_roll 仅限 RITUAL_ROOMS
}

# 数据层未声明、handler 写死的「必须在该房间」（房间 id, 依据）
HANDLER_REQUIRED = {
    34: ("vault", "lock_up 仅在保险库可用且要求 room.data['opened']（haunt_34 L250/L271）"),
}


def _walk(node, path, hits):
    """递归收集字符串值命中四房 id 的 JSON 路径。"""
    if isinstance(node, dict):
        for key, value in node.items():
            _walk(value, "%s.%s" % (path, key) if path else str(key), hits)
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            _walk(value, "%s[%d]" % (path, index), hits)
    elif isinstance(node, str):
        for room in PHOTOS_ROOMS:
            if re.search(r"\b%s\b" % room, node):
                hits.append({"path": path, "room": room, "value": node})


def _handler_path(game_dir: Path, haunt_id: int):
    matches = sorted((game_dir / "haunts").glob("haunt_%02d_*.py" % haunt_id))
    return matches[0] if matches else None


def _scan_handler(path: Path):
    """返回 {room: [(行号, 行文本)]}，只取字符串字面量或标识符出现的行。"""
    result = {}
    if path is None:
        return result
    lines = path.read_text(encoding="utf-8").splitlines()
    for number, text in enumerate(lines, 1):
        for room in PHOTOS_ROOMS:
            if re.search(r"[\"']%s[\"']" % room, text):
                result.setdefault(room, []).append([number, text.strip()])
    return result


def _classify_rule_hits(hits, rule, haunt_id):
    """把规则字典里的命中归类，并给出「胜利必需房」判定。

    返回 {room: {"uses": [...], "necessary": "是"/"间接", "evidence": "..."}}。
    """
    terminal = set(TERMINAL_ACTIONS.get(haunt_id, ()))
    per_room = {}
    for hit in hits:
        path, room = hit["path"], hit["room"]
        bucket = per_room.setdefault(room, {"uses": [], "necessary": "间接", "evidence": ""})
        if path.startswith("key_rooms"):
            bucket["uses"].append("key_rooms")
        elif path.startswith("win_conditions"):
            bucket["uses"].append("victory:%s" % path)
            bucket["necessary"] = "是"
            bucket["evidence"] = "win_conditions:" + path
        elif re.match(r"^actions\[\d+\]\.rooms", path):
            index = int(re.match(r"^actions\[(\d+)\]", path).group(1))
            action = (rule.get("actions") or [])[index]
            action_id = action.get("id") or "actions[%d]" % index
            bucket["uses"].append("actions.rooms:%s" % action_id)
            if action_id in terminal:
                bucket["necessary"] = "是"
                bucket["evidence"] = "终局动作 %s 的 rooms 含该房（handler check_victory 以它判胜）" % action_id
        elif path.startswith("setup.tracks"):
            bucket["uses"].append("tracks:%s" % path)
        elif path.startswith("actions"):
            bucket["uses"].append("actions.other:%s" % path)
        else:
            bucket["uses"].append("other:%s" % path)

    # handler 写死的房间前置（数据层没声明）
    required = HANDLER_REQUIRED.get(haunt_id)
    if required:
        room, why = required
        bucket = per_room.setdefault(room, {"uses": [], "necessary": "间接", "evidence": ""})
        bucket["necessary"] = "是"
        bucket["uses"].append("handler:required")
        bucket["evidence"] = why
    return per_room


def main() -> int:
    sys.path.insert(0, str(GAME_DIR))
    import haunt_rules  # noqa: E402  （只读导入，不构造引擎）
    import content  # noqa: E402

    catalog = content.build_catalog(0)
    rows = []
    for haunt_id in range(1, 71):
        rule = haunt_rules.get_haunt_rule_override(haunt_id)
        name = getattr(catalog.haunt_defs.get(haunt_id), "name", "")
        hits = []
        _walk(rule, "", hits)
        per_room = _classify_rule_hits(hits, rule, haunt_id)
        handler = _handler_path(GAME_DIR, haunt_id)
        code_hits = _scan_handler(handler)
        for room in PHOTOS_ROOMS:
            if room in code_hits and room not in per_room:
                # 只在 handler 代码里出现，规则字典里没有
                per_room[room] = {"uses": [], "necessary": "间接", "evidence": ""}
                per_room[room]["uses"].append(
                    "handler:%s:%d" % (handler.name, code_hits[room][0][0]))
        if not per_room:
            continue
        rows.append(
            {
                "haunt_id": haunt_id,
                "name": name,
                "mode": rule.get("mode", ""),
                "handler": handler.name if handler else "",
                "win_conditions": [
                    {key: value for key, value in condition.items()
                     if key in ("winner", "type", "track", "target", "reason")}
                    for condition in (rule.get("win_conditions") or [])
                    if isinstance(condition, dict)
                ],
                "tracks": list(((rule.get("setup") or {}).get("tracks") or {}).keys()),
                "actions": [
                    {"id": action.get("id", ""), "progress": action.get("progress", ""),
                     "rooms": action.get("rooms", [])}
                    for action in (rule.get("actions") or []) if isinstance(action, dict)
                ],
                "rooms": {
                    room: {
                        "uses": sorted(set(info["uses"])),
                        "necessary": info["necessary"],
                        "evidence": info.get("evidence", ""),
                        "handler_lines": code_hits.get(room, []),
                    }
                    for room, info in sorted(per_room.items())
                },
            }
        )

    summary = {"是": [], "间接": []}
    per_room_count = {room: 0 for room in PHOTOS_ROOMS}
    per_room_necessary = {room: 0 for room in PHOTOS_ROOMS}
    verdict_rows = {"是": [], "间接": [], "无关": []}
    for row in rows:
        worst = "间接"
        for room, info in row["rooms"].items():
            per_room_count[room] += 1
            summary[info["necessary"]].append((row["haunt_id"], room))
            if info["necessary"] == "是":
                per_room_necessary[room] += 1
                worst = "是"
        row["verdict"] = worst
        verdict_rows[worst].append(row["haunt_id"])
    hit_ids = {row["haunt_id"] for row in rows}
    verdict_rows["无关"] = [n for n in range(1, 71) if n not in hit_ids]

    document = {
        "generated_by": "qa/k2_haunt_scan.py（只读扫描 haunt_rules + haunts/*.py）",
        "rooms": list(PHOTOS_ROOMS),
        "criteria": {
            "necessary": "房间出现在 win_conditions，或出现在结束对局的行动 rooms 里，"
                         "或 handler 写死为胜利前置",
            "indirect": "只出现在 key_rooms / 前置搜寻与生成 / 非终局 actions.rooms / "
                        "tracks 标签 / handler 常量",
            "haunt_level": "一本剧本命中多间房时取最强判定（是 > 间接 > 无关）",
        },
        "manual_inputs": {
            "terminal_actions": {str(k): list(v) for k, v in TERMINAL_ACTIONS.items()},
            "handler_required": {str(k): list(v) for k, v in HANDLER_REQUIRED.items()},
        },
        "totals": {
            "haunts_total": 70,
            "haunts_hit": len(rows),
            "necessary_pairs": len(summary["是"]),
            "indirect_pairs": len(summary["间接"]),
            "per_room": per_room_count,
            "per_room_necessary": per_room_necessary,
            "verdict_haunts": {key: len(value) for key, value in verdict_rows.items()},
        },
        "verdicts": {key: value for key, value in verdict_rows.items()},
        "haunts": rows,
    }
    OUT_PATH.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("命中剧本 %d/70；必需房对 %d，间接房对 %d"
          % (len(rows), len(summary["是"]), len(summary["间接"])))
    print("逐房命中本数：" + "  ".join("%s=%d" % (r, c) for r, c in per_room_count.items()))
    print("逐房必需本数：" + "  ".join("%s=%d" % (r, c) for r, c in per_room_necessary.items()))
    print("剧本级判定：必需 %d 本 / 间接 %d 本 / 无关 %d 本"
          % (len(verdict_rows["是"]), len(verdict_rows["间接"]), len(verdict_rows["无关"])))
    print("必需剧本号：%s" % (verdict_rows["是"] or "无"))
    print("")
    for row in rows:
        marks = ", ".join(
            "%s(%s)" % (room, info["necessary"]) for room, info in row["rooms"].items())
        print("  #%-2d %-28s %-24s %s" % (row["haunt_id"], row["name"][:26],
                                          row["mode"][:24], marks))
    print("")
    print("写出 %s" % OUT_PATH.relative_to(GAME_DIR).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
