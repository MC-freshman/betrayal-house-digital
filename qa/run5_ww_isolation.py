#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run5 S1：Widow's Walk 内容隔离（一次性迁移工具，可重复执行需 --force）。

做什么
------
1. S0 归档：``content.py`` / ``haunt_rules.py`` / ``haunts/__init__.py`` 原样复制到
   ``_freeze/``，供 A-29 判据 4 做 **id 集合相等** 比对（不删内容）。
2. 生成 ``content_ww.py``：把 ``content.py`` 里的 20 屋顶房 / 15 事件 / 10 物品 /
   5 预兆 / 50 剧本（槽位 71-120）迁入，并接管 ``FLOOR_ROOF`` /
   ``ROOF_ROOM_IDS`` / ``WW_EVENT_ADDITION`` / ``_roof_room_def``。
3. ``content.py`` 收敛为 142 位基线（12/50/45/22/13/70）。
4. ``haunt_rules.py`` 的 WW 剧本规则表（槽位 71-120）迁到 ``content_ww.py``，
   ``get_haunt_rule_override`` 只服务 1-70。
5. ``haunts/__init__.py`` 不再注册 / 导入 50 个 WW handler，注册表回到 70 本。
6. ``haunts/haunt_haunt71-120.py`` → ``haunts/_ww_deferred/``（保留、不删除）。
7. ``haunts_zh/haunt_71-120.md`` → ``haunts_zh/_ww_deferred/``。
8. ``assets/placeholders/ww_*.png``（50 张）→ ``assets_ww/placeholders/``
   （run5 验收 §1.2 B-05：``assets/`` 下不得再有 WW 运行时资源）。

证据
----
``qa/run5_ww_isolation.json``：逐项 before/after 计数、sha256、id 集合 diff、
动作清单。本脚本只写 ``_freeze/``、``content_ww.py``、``content.py``、
``haunt_rules.py``、``haunts/__init__.py`` 与两个 ``_ww_deferred`` 目录 + 迁移清单。

用法::

    python qa/run5_ww_isolation.py            # 首次执行
    python qa/run5_ww_isolation.py --dry-run  # 只打印计划
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GAME_DIR.parents[2]
QA_DIR = Path(__file__).resolve().parent
FREEZE_DIR = PROJECT_ROOT / "_freeze"
ASSETS_WW_DIR = GAME_DIR / "assets_ww"

CONTENT_PY = GAME_DIR / "content.py"
CONTENT_WW_PY = GAME_DIR / "content_ww.py"
HAUNT_RULES_PY = GAME_DIR / "haunt_rules.py"
HAUNTS_INIT_PY = GAME_DIR / "haunts" / "__init__.py"
HAUNTS_DIR = GAME_DIR / "haunts"
HAUNTS_ZH_DIR = GAME_DIR / "haunts_zh"
PLACEHOLDER_DIR = GAME_DIR / "assets" / "placeholders"
EVIDENCE_JSON = QA_DIR / "run5_ww_isolation.json"

WW_HAUNT_IDS = list(range(71, 121))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_lines(path: Path) -> list:
    """按 \\n 切分但保留每行自身的行尾信息（本仓库用 LF / CRLF 混排）。"""
    raw = path.read_bytes().decode("utf-8")
    return raw.split("\n") if "\r\n" not in raw else raw.replace("\r\n", "\n").split("\n")


def write_text(path: Path, text: str, crlf: bool) -> None:
    data = text.replace("\n", "\r\n") if crlf else text
    path.write_bytes(data.encode("utf-8"))


def expect(lines: list, lineno: int, needle: str, label: str) -> None:
    """行号锚点自检：迁移脚本宁可中止，也不要把行切错。"""
    actual = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
    if needle not in actual:
        raise SystemExit("锚点失配 %s：第 %d 行期望含 %r，实际 %r"
                         % (label, lineno, needle, actual[:120]))


# ----------------------------------------------------------------------
# content.py → content_ww.py
# ----------------------------------------------------------------------
def build_content_ww(content_lines: list, haunt_rules_lines: list, archived_sha: str) -> str:
    omen_body = content_lines[552:607]        # 553..607
    item_body = content_lines[845:941]        # 846..941
    event_body = content_lines[1500:1515]     # 1501..1515
    roof_block = content_lines[1532:1801]     # 1533..1801（注释 + ROOF_ROOMS + ROOF_ROOM_IDS + WW_EVENT_ADDITION）
    haunt_body = content_lines[2015:2065]     # 2016..2065

    expect(content_lines, 553, "card_def(", "omen 起点")
    expect(content_lines, 554, 'card_id="omen_bloodstone"', "omen 首张")
    expect(content_lines, 607, "    ),", "omen 终点")
    expect(content_lines, 846, "card_def(", "item 起点")
    expect(content_lines, 847, 'card_id="item_blueprint"', "item 首张")
    expect(content_lines, 941, "    ),", "item 终点")
    expect(content_lines, 1501, '("event_contract"', "event 起点")
    expect(content_lines, 1515, "event_the_left_hand_writes", "event 终点")
    expect(content_lines, 1553, "ROOF_ROOMS = [", "roof 起点")
    expect(content_lines, 1797, "ROOF_ROOM_IDS = tuple", "roof ids")
    expect(content_lines, 1801, "WW_EVENT_ADDITION = 15", "ww 事件张数")
    expect(content_lines, 2016, '(71, "Director', "haunt 起点")
    expect(content_lines, 2065, '(120, "Let', "haunt 终点")

    ww_rules_block = haunt_rules_lines[3843:4483]   # 3844..4483（注释 + 表 + 规则字典）
    expect(haunt_rules_lines, 3844, "# ------", "ww 规则表头")
    expect(haunt_rules_lines, 3861, "_WW_SCENARIO_TABLE", "ww 规则表")
    expect(haunt_rules_lines, 4483, "}", "ww 规则表尾")
    ww_rules_text = "\n".join(ww_rules_block).replace(
        "_WW_SCENARIO_TABLE", "WW_SCENARIO_TABLE")
    ww_rules_text = ww_rules_text.replace(
        "#   ROOF_ROOMS，即\"屋顶层条件剧本\"），required_cards 只列本仓库存在的卡，",
        "#   content_ww.ROOF_ROOMS，即\"屋顶层条件剧本\"），required_cards 只列本仓库存在的卡，")

    roof_text = "\n".join(roof_block).replace(
        "ROOF_ROOM_IDS = tuple(spec[\"id\"] for spec in ROOF_ROOMS)",
        "ROOF_ROOM_IDS = tuple(spec[\"id\"] for spec in ROOF_ROOMS)")

    header = '''#!/usr/bin/env python
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
``_freeze/content_pre_run5.py``，sha256=%(sha)s；id 集合相等性见
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
''' % {"sha": archived_sha}

    body_omen = "\n".join(omen_body) + "\n]\n"

    part_item = '''
# ======================================================================
# 2) 物品 10 张（官方 11 张，Dynamite 与基础版重名不重复登记）
# ======================================================================
WW_ITEM_ADDITIONS = [
''' + "\n".join(item_body) + "\n]\n"

    part_event = '''
# ======================================================================
# 3) 事件 15 张（事件位 45→60 超出部分；effect_id 复用基础事件效果）
# ======================================================================
WW_EVENT_ADDITIONS = [
''' + "\n".join(event_body) + "\n]\n"

    part_roof = "\n" + roof_text + "\n"

    part_roof_helper = '''
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
''' + "\n".join(haunt_body) + "\n]\n"

    part_names = '''
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
''' + ww_rules_text + '''


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
'''

    return header + body_omen + part_item + part_event + part_roof + part_roof_helper + part_names


def trim_content(content_lines: list) -> str:
    """content.py 收敛为 142 位基线。"""
    drop = set()

    def mark(start: int, end: int) -> None:
        for i in range(start, end + 1):
            drop.add(i)

    # 1) 楼层枚举的 WW 注释 + FLOOR_ROOF
    expect(content_lines, 45, "楼层枚举", "楼层注释")
    expect(content_lines, 54, 'FLOOR_ROOF = "roof"', "FLOOR_ROOF")
    mark(54, 54)
    # 2) 预兆 WW 5 条（注释 548-552 + 5 张卡 553-607）
    expect(content_lines, 548, "# ------", "预兆 WW 注释")
    mark(548, 607)
    # 3) 物品 WW 10 条
    expect(content_lines, 840, "# ------", "物品 WW 注释")
    mark(840, 941)
    # 4) 事件 WW 15 条
    expect(content_lines, 1494, "# ------", "事件 WW 注释")
    mark(1494, 1515)
    # 5) ROOF_ROOMS + ROOF_ROOM_IDS + WW_EVENT_ADDITION + _roof_room_def
    expect(content_lines, 1533, "# ------", "roof 注释")
    expect(content_lines, 1817, 'tags=("roof", "widows_walk")', "_roof_room_def")
    mark(1533, 1820)
    # 6) 剧本名 71-120
    expect(content_lines, 2012, "# ------", "剧本 WW 注释")
    mark(2012, 2065)

    kept = [line for idx, line in enumerate(content_lines, start=1) if idx not in drop]
    text = "\n".join(kept)

    # 7) build_catalog 去 WW 分支
    replacements = [
        (
            "    # 基础版事件总数为 45（EVENT_BASES + 补充事件）；Widow's Walk 再加入\n"
            "    # WW_EVENT_ADDITION 张新事件，事件牌堆扩到 60 张。\n"
            "    event_target = 45 + WW_EVENT_ADDITION\n",
            "    # 基础版事件总数为 45（EVENT_BASES + 补充事件）。\n"
            "    # run5：Widow's Walk 的 15 张新事件已隔离到 content_ww.py，不再计入。\n"
            "    event_target = 45\n",
        ),
        (
            "    # Widow's Walk 屋顶层：20 块扩充板块进入房间模板全集；基础层的\n"
            "    # room_draw_pool 保持不变（旧对局的房间序列零漂移），屋顶层的抽取由\n"
            "    # 引擎从 ROOF_ROOM_IDS 独立建牌堆。Roof Landing 开局即入局，不进抽牌池。\n"
            "    roof_room_specs = [_roof_room_def(spec) for spec in ROOF_ROOMS]\n"
            "    for spec in roof_room_specs:\n"
            "        room_template_specs.append(spec)\n"
            "        room_template_map[spec[\"id\"]] = spec\n\n",
            "    # run5：Widow's Walk 屋顶层 20 块板块已隔离到 content_ww.py；\n"
            "    # ROOM_BASES(39) + ROOM_SUPPLEMENTAL_SPECS(11) = 50 个房间模板。\n\n",
        ),
        (
            "        if room_id not in start_ids and room_id not in set(ROOF_ROOM_IDS)\n",
            "        if room_id not in start_ids\n",
        ),
        (
            '        start_room_ids=["basement_landing", "entrance_hall", "foyer", "grand_staircase", "upper_landing", "roof_landing"],\n',
            '        start_room_ids=["basement_landing", "entrance_hall", "foyer", "grand_staircase", "upper_landing"],\n',
        ),
        (
            "# 楼层枚举（Widow's Walk 扩充）\n"
            "# ----------------------------------------------------------------------\n"
            "# 基础版楼层沿用整数约定（-1=地下室 / 0=一层 / 1=二层），引擎内\n"
            "# _room_key / pos_index 直接拼 key，不需要连续整数。屋顶层是新楼层，\n"
            "# 采用独立字符串值，避免与基础版三层的算术假设（floor±1 等）互相污染：\n"
            "# 屋顶房的抽取、放置与探索全部按\"floor == FLOOR_ROOF\"等值比较走独立分支。\n",
            "# 楼层枚举（基础版三层；WW 屋顶层见 content_ww.FLOOR_ROOF）\n"
            "# ----------------------------------------------------------------------\n"
            "# 基础版楼层沿用整数约定（-1=地下室 / 0=一层 / 1=二层），引擎内\n"
            "# _room_key / pos_index 直接拼 key，不需要连续整数。\n"
            "# run5：WW 屋顶层（独立字符串值 \"roof\"）已随 20 块板块隔离到 content_ww.py。\n",
        ),
    ]
    for old, new in replacements:
        if old not in text:
            raise SystemExit("build_catalog 替换锚点缺失：%r" % old[:80])
        text = text.replace(old, new, 1)
    return text


# ----------------------------------------------------------------------
# haunt_rules.py / haunts/__init__.py
# ----------------------------------------------------------------------
def trim_haunt_rules(lines: list) -> str:
    expect(lines, 3844, "# ------", "haunt_rules WW 表头")
    expect(lines, 3861, "_WW_SCENARIO_TABLE", "haunt_rules WW 表")
    expect(lines, 4483, "}", "haunt_rules WW 表尾")
    expect(lines, 4485, "", "haunt_rules 空行")
    kept = [line for idx, line in enumerate(lines, start=1)
            if not 3844 <= idx <= 4484]
    text = "\n".join(kept)
    text = text.replace(
        "    rule = HAUNT_RULE_OVERRIDES.get(haunt_id) or SUPPLEMENTAL_HAUNT_RULES.get(haunt_id, {}) or WW_HAUNT_RULES.get(haunt_id, {})",
        "    rule = HAUNT_RULE_OVERRIDES.get(haunt_id) or SUPPLEMENTAL_HAUNT_RULES.get(haunt_id, {})")
    text = text.replace(
        '    """返回隐藏规则表；1-10 使用专属实现，11-70 使用逐号结构化规则，\n'
        '    71-120 为 Widow\'s Walk 剧本骨架。"""',
        '    """返回隐藏规则表；1-10 使用专属实现，11-70 使用逐号结构化规则。\n\n'
        '    run5：槽位 71-120（Widow\'s Walk）的剧本骨架已隔离到\n'
        '    ``content_ww.WW_HAUNT_RULES``，本函数不再加载它们。\n'
        '    """')
    return text


def trim_haunts_init(lines: list) -> str:
    drop = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if any(stripped == '"haunt_haunt%d",' % sid for sid in WW_HAUNT_IDS):
            drop.append(idx)
        elif any(stripped.startswith("from .haunt_haunt%d import WWHaunt%dMode" % (sid, sid))
                 for sid in WW_HAUNT_IDS):
            drop.append(idx)
        elif any(stripped == '"WWHaunt%dMode",' % sid for sid in WW_HAUNT_IDS):
            drop.append(idx)
    if len(drop) != 3 * len(WW_HAUNT_IDS):
        raise SystemExit("haunts/__init__.py WW 行数异常：%d（期望 %d）"
                         % (len(drop), 3 * len(WW_HAUNT_IDS)))
    kept = [line for idx, line in enumerate(lines, start=1) if idx not in set(drop)]
    return "\n".join(kept)


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="run5 WW 内容隔离")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不写文件")
    parser.add_argument("--force", action="store_true", help="已隔离时强制重跑")
    args = parser.parse_args(argv)

    already = CONTENT_WW_PY.is_file()
    if already and not args.force:
        print("[skip] content_ww.py 已存在：%s" % CONTENT_WW_PY)
        print("       如需重跑请加 --force（会覆盖 content_ww.py 并重做迁移）")
        return 0

    content_raw = CONTENT_PY.read_bytes()
    haunt_rules_raw = HAUNT_RULES_PY.read_bytes()
    haunts_init_raw = HAUNTS_INIT_PY.read_bytes()
    content_lines = read_lines(CONTENT_PY)
    haunt_rules_lines = read_lines(HAUNT_RULES_PY)
    haunts_init_lines = read_lines(HAUNTS_INIT_PY)

    content_sha = sha256_bytes(content_raw)
    print("[S0] content.py sha256=%s（%d 行）" % (content_sha, len(content_lines)))

    content_ww_text = build_content_ww(content_lines, haunt_rules_lines, content_sha)
    trimmed_content = trim_content(content_lines)
    trimmed_rules = trim_haunt_rules(haunt_rules_lines)
    trimmed_init = trim_haunts_init(haunts_init_lines)

    if args.dry_run:
        print("[dry-run] content_ww.py %d 行 / content.py %d 行 / haunt_rules.py %d 行 / haunts/__init__.py %d 行"
              % (content_ww_text.count("\n") + 1, trimmed_content.count("\n") + 1,
                 trimmed_rules.count("\n") + 1, trimmed_init.count("\n") + 1))
        return 0

    # S0 归档（原样字节，供 id 集合比对与回滚）
    FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    for name, raw in (
        ("content_pre_run5.py", content_raw),
        ("haunt_rules_pre_run5.py", haunt_rules_raw),
        ("haunts_init_pre_run5.py", haunts_init_raw),
    ):
        (FREEZE_DIR / name).write_bytes(raw)
    print("[S0] 归档 -> %s" % FREEZE_DIR)

    # 1) content_ww.py（LF）
    write_text(CONTENT_WW_PY, content_ww_text, crlf=False)
    print("[1] content_ww.py %d 行" % (content_ww_text.count("\n") + 1))

    # 2) content.py 收敛（原文件为 LF）
    write_text(CONTENT_PY, trimmed_content, crlf=False)
    print("[2] content.py %d 行" % (trimmed_content.count("\n") + 1))

    # 3) haunt_rules.py（CRLF）
    write_text(HAUNT_RULES_PY, trimmed_rules, crlf=True)
    print("[3] haunt_rules.py %d 行" % (trimmed_rules.count("\n") + 1))

    # 4) haunts/__init__.py（CRLF）
    write_text(HAUNTS_INIT_PY, trimmed_init, crlf=True)
    print("[4] haunts/__init__.py %d 行" % (trimmed_init.count("\n") + 1))

    # 5) 50 个 WW handler → haunts/_ww_deferred/
    deferred_haunts = HAUNTS_DIR / "_ww_deferred"
    deferred_haunts.mkdir(exist_ok=True)
    moved_haunts = []
    for sid in WW_HAUNT_IDS:
        src = HAUNTS_DIR / ("haunt_haunt%d.py" % sid)
        dst = deferred_haunts / src.name
        if src.is_file():
            shutil.move(str(src), str(dst))
            moved_haunts.append({"file": src.name, "sha256": sha256_file(dst)})
    print("[5] haunts/_ww_deferred/ %d 个模块" % len(moved_haunts))

    # 6) haunts_zh 中文手册 71-120
    deferred_zh = HAUNTS_ZH_DIR / "_ww_deferred"
    deferred_zh.mkdir(exist_ok=True)
    moved_zh = []
    for sid in WW_HAUNT_IDS:
        src = HAUNTS_ZH_DIR / ("haunt_%02d.md" % sid)
        dst = deferred_zh / src.name
        if src.is_file():
            shutil.move(str(src), str(dst))
            moved_zh.append({"file": src.name, "sha256": sha256_file(dst)})
    print("[6] haunts_zh/_ww_deferred/ %d 本手册" % len(moved_zh))

    # 7) 50 张 ww_* 占位图 → assets_ww/placeholders/
    ww_placeholder_dir = ASSETS_WW_DIR / "placeholders"
    ww_placeholder_dir.mkdir(parents=True, exist_ok=True)
    moved_placeholders = []
    for src in sorted(PLACEHOLDER_DIR.glob("ww_*.png")):
        dst = ww_placeholder_dir / src.name
        shutil.move(str(src), str(dst))
        moved_placeholders.append({"file": src.name, "sha256": sha256_file(dst)})
    print("[7] assets_ww/placeholders/ %d 张 WW 占位图" % len(moved_placeholders))

    # 证据
    evidence = {
        "schema": "run5_ww_isolation/v1",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "python": sys.version.split()[0],
        "s0_archive": {
            "content_pre_run5.py": content_sha,
            "haunt_rules_pre_run5.py": sha256_bytes(haunt_rules_raw),
            "haunts_init_pre_run5.py": sha256_bytes(haunts_init_raw),
        },
        "after_sha256": {
            "content.py": sha256_file(CONTENT_PY),
            "content_ww.py": sha256_file(CONTENT_WW_PY),
            "haunt_rules.py": sha256_file(HAUNT_RULES_PY),
            "haunts/__init__.py": sha256_file(HAUNTS_INIT_PY),
        },
        "lines": {
            "content.py": {"before": len(content_lines),
                           "after": trimmed_content.count("\n") + 1},
            "haunt_rules.py": {"before": len(haunt_rules_lines),
                               "after": trimmed_rules.count("\n") + 1},
        },
        "moved_haunts": moved_haunts,
        "moved_haunts_zh": moved_zh,
        "moved_placeholders": moved_placeholders,
        "counts": {
            "moved_haunt_modules": len(moved_haunts),
            "moved_haunt_manuals": len(moved_zh),
            "moved_ww_placeholders": len(moved_placeholders),
        },
    }
    EVIDENCE_JSON.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print("[evidence] %s" % EVIDENCE_JSON)
    return 0


if __name__ == "__main__":
    sys.exit(main())
