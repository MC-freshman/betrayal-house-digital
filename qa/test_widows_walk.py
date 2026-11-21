#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Widow's Walk 扩充验收测试（WW-T01…T05 单元/集成层 · 只读设计）。

范围与语义
----------
* 覆盖验收标准（``.codebuddy/wfat/ww_acceptance_criteria.md`` §3）中的
  WW-T01（屋顶层放置）、WW-T02（剧本 71–120 触发）、WW-T03（新卡牌效果）、
  WW-T04（屋顶满边界）、WW-T05（P 表 192 位计数）；
* WW-T06…T10（异常注入 / 回归 / 性能 / UI / AI 图）为验收脚本层，不在本文件，
  详见 ``docs/qa_widows_walk.md``；
* **只读设计**：本文件不写 assets/、不重建 P 表、不调用会落盘的 CLI；
  ``haunt_playtest.run_case`` 为内存对局驱动，仅 ``--json-path`` 时才写文件。
* SKIP 不是 PASS：WW 实现（屋顶层 / 槽位 71–120 / 新卡 / 192 位 P 表）尚未
  落地时，对应用例逐条 SKIP 并在消息中列出实测缺口（方法级 skip，报告逐条
  留痕）；验收（A-31）以实现合入后的全量 PASS 为准，未执行项记 not-run，
  不折算 PASS。

就绪探测（兼容三种屋顶实现方式）
--------------------------------
1. ``content.FLOOR_ROOF`` 常量（架构文件声明的接口，值任意）；
2. ``Catalog.room_targets`` 键域扩展出 {-1, 0, 1} 之外的新楼层键；
3. ``RoomTemplate.floor`` 出现基线值域之外的新值。
基线楼层为整数：-1=地下 / 0=地面 / 1=二层（实测 content.room_targets）。

跑法（game 目录下）::

    python -B -m unittest qa.test_widows_walk -v
    python qa/test_widows_walk.py

只读输入：assets/p_table.json、haunts/*.py、.codebuddy/wfat/ww_official_content.json、
（可选）qa/fixtures/ww_baseline_record_ids_142.json（T05 零漂移基线快照，
由验收执行脚本一次性导出；缺失时零漂移子项记 SKIP，不冒充 PASS）。
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import unittest
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GAME_DIR.parents[2]
QA_DIR = Path(__file__).resolve().parent
FIXTURES = QA_DIR / "fixtures"
PTABLE_JSON = GAME_DIR / "assets" / "p_table.json"
OFFICIAL_WW_JSON = PROJECT_ROOT / ".codebuddy" / "wfat" / "ww_official_content.json"
BASELINE_IDS_SNAPSHOT = FIXTURES / "ww_baseline_record_ids_142.json"

if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

# Windows 控制台 GBK 兜底：失败消息含中文时避免 UnicodeEncodeError。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - 环境差异，尽力而为
            pass

import content  # noqa: E402
from content import (  # noqa: E402
    EVENT_BASES,
    HAUNT_NAMES,
    ITEM_CARDS,
    OMEN_CARDS,
    ROOM_BASES,
    build_catalog,
)
from models import Catalog  # noqa: E402
import haunt_rules  # noqa: E402
import engine as engine_mod  # noqa: E402

GameEngine = engine_mod.GameEngine

# ---------------------------------------------------------------- 常量（口径锚点）
# 基线楼层：实测 content.room_targets = {-1: 12, 0: 20, 1: 12}
BASELINE_FLOORS = {-1, 0, 1}
# 基线锚点：p_table_execution_final.json（report_id=p-table-final-20261120T174245，
# verdict=PASS，claim=attested，2026-11-20 实测）
BASELINE_PT_RECORDS = 142
BASELINE_PT_STATS = {
    "usable": 0,
    "partial": 95,
    "missing": 47,
    "corrupted": 0,
    "duplicate": 0,
    "placeholder_records": 31,
    "fallback_records": 16,
}
BASELINE_PT_BY_TYPE = {
    "character": 12,
    "room": 50,
    "card_omen": 13,
    "card_item": 22,
    "card_event": 45,
}
# 基线 content 集合计数（2026-11-20 实测；EVENT_BASES=11 与 P 表 card_event=45
# 口径分裂，见 docs/qa_widows_walk.md §R3）
BASELINE_CONTENT_COUNTS = {"event": len(EVENT_BASES), "item": len(ITEM_CARDS), "omen": len(OMEN_CARDS)}
# WW 目标（验收标准 §1.1 / §3，冻结判据）
WW_PT_RECORDS = 192
WW_PT_BY_TYPE = {
    "character": 12,
    "room": 70,
    "card_event": 60,
    "card_item": 32,
    "card_omen": 18,
}
WW_PT_STATS = {
    "usable": 192,
    "partial": 0,
    "missing": 0,
    "corrupted": 0,
    "duplicate": 0,
    "placeholder_records": 0,
    "fallback_records": 0,
}
# 冻结卡牌目标（content 集合口径，T03-④：content 计数与 P 表分类计数一致）
WW_CARD_TARGETS = {"event": 60, "item": 32, "omen": 18}
# WW 剧本槽位：团队槽位 71–120 ↔ 官方编号 51–100（ww_official_content.json meta）
WW_HAUNT_SLOTS = tuple(range(71, 121))
BASELINE_HAUNT_SLOTS = tuple(range(1, 71))
# T01 种子遍历：验收判据"≥50 个随机种子遍历 0 异常 0 traceback"
WW_T01_SEEDS = tuple(range(1001, 1051))


# ---------------------------------------------------------------- 只读辅助
def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_official_ww() -> dict | None:
    """读冻结官方清单；缺失返回 None（调用方据实 SKIP，不猜测）。"""
    if not OFFICIAL_WW_JSON.exists():
        return None
    try:
        return _load_json(OFFICIAL_WW_JSON)
    except Exception:
        return None


def _player_configs(engine: GameEngine, count: int = 4) -> list[dict]:
    faces = list(engine.catalog.characters)
    return [
        {"name": "P%d" % (i + 1), "character_id": faces[i % len(faces)], "control": "human"}
        for i in range(count)
    ]


def _new_game(seed: int, players: int = 4) -> GameEngine:
    engine = GameEngine(seed=seed)
    engine.start_new_game(_player_configs(engine, players))
    return engine


def _detect_roof(catalog: Catalog):
    """探测屋顶层。返回 (roof_floor, roof_pool, probe_note)。

    roof_floor 为 None 表示屋顶层未就绪；probe_note 携带实测缺口数据。
    roof_pool: {template_id: RoomTemplate}，按模板 floor 归属过滤。
    """
    probes: list[str] = []
    roof = getattr(content, "FLOOR_ROOF", None)
    if roof is not None:
        pool = {tid: t for tid, t in catalog.room_templates.items() if t.floor == roof}
        if pool:
            return roof, pool, "content.FLOOR_ROOF=%r" % (roof,)
        probes.append("content.FLOOR_ROOF=%r 但无模板归属该层" % (roof,))
    target_extra = set(catalog.room_targets) - BASELINE_FLOORS
    template_extra = {t.floor for t in catalog.room_templates.values()} - BASELINE_FLOORS
    int_candidates = sorted(f for f in (target_extra | template_extra) if isinstance(f, int))
    str_candidates = sorted(f for f in (target_extra | template_extra) if isinstance(f, str))
    for floor in str_candidates + (int_candidates[::-1] if int_candidates else []):
        pool = {tid: t for tid, t in catalog.room_templates.items() if t.floor == floor}
        if pool:
            return floor, pool, "新楼层 %r（room_targets=%r）" % (floor, catalog.room_targets)
    if target_extra or template_extra:
        probes.append("新楼层键 %r/%r 存在但无模板归属" % (sorted(target_extra), sorted(template_extra)))
    probes.append("room_targets=%r 无 {-1,0,1} 之外的键" % (catalog.room_targets,))
    probes.append("content 无 FLOOR_ROOF 属性")
    return None, {}, "；".join(probes)


_EFFECT_SRC_CACHE: dict[str, str] = {}


def _effect_source() -> str:
    """收集全部效果解析源码（引擎 + engine_parts + 剧本 handler + AI + 帮助文本）。

    效果解析为分散式（engine._resolve_event / engine_parts.room_effects
    ._apply_room_effect / haunt_modes 与 haunts/*.py 的 handler /
    数据驱动 bonus/tags），"未知 effect_id"判定必须覆盖全范围。
    """
    if "src" in _EFFECT_SRC_CACHE:
        return _EFFECT_SRC_CACHE["src"]
    chunks: list[str] = []
    patterns = [
        sorted(GAME_DIR.glob("*.py")),
        sorted((GAME_DIR / "haunts").glob("haunt_*.py")),
        sorted((GAME_DIR / "haunts").glob("base.py")),
        sorted((GAME_DIR / "ai").glob("*.py")),
        sorted((GAME_DIR / "engine_parts").glob("*.py")),
    ]
    for group in patterns:
        for path in group:
            try:
                chunks.append(path.read_text(encoding="utf-8"))
            except Exception:  # pragma: no cover - 编码异常文件按内容缺失处理
                continue
    _EFFECT_SRC_CACHE["src"] = "\n".join(chunks)
    return _EFFECT_SRC_CACHE["src"]


def _all_cards() -> list[dict]:
    return list(EVENT_BASES) + list(ITEM_CARDS) + list(OMEN_CARDS)


def _unknown_effect_ids(card_dicts: list[dict], include_rooms: bool = False) -> list[str]:
    pool = list(card_dicts) + (list(ROOM_BASES) if include_rooms else [])
    ids = {c["effect_id"] for c in pool if c.get("effect_id") not in ("generic", "none")}
    src = _effect_source()
    return sorted(i for i in ids if i not in src)


def _ww_haunt_slots() -> tuple[list[int], str]:
    """探测 WW 剧本槽位就绪度。返回 (已见槽位列表, 缺口说明)。"""
    seen: set[int] = set()
    for slot, _name in HAUNT_NAMES:
        if isinstance(slot, int) and slot > 70:
            seen.add(slot)
    rules = getattr(haunt_rules, "HAUNT_RULE_OVERRIDES", {})
    for slot in rules:
        if isinstance(slot, int) and slot > 70:
            seen.add(slot)
    haunts_dir = GAME_DIR / "haunts"
    for path in haunts_dir.glob("haunt_*.py"):
        m = re.match(r"haunt_(\d+)_", path.name)
        if m and int(m.group(1)) > 70:
            seen.add(int(m.group(1)))
    missing = [s for s in WW_HAUNT_SLOTS if s not in seen]
    note = (
        "已见 WW 槽位 %d/50（%s）；缺失 %d 个"
        % (len(seen), sorted(seen)[:12] or "无", len(missing))
    )
    return sorted(seen), note


class _WWReadyMixin:
    """就绪探测混入：探测结果类级缓存，SKIP 逐方法上报（报告逐条留痕）。

    子类覆盖 ``_ready_probe()``：返回 None = 就绪；返回字符串 = 全类 SKIP 原因。
    探测过程中的非法中间态直接 raise AssertionError（计 FAIL，不折算 SKIP）。
    """

    @classmethod
    def _ready_probe(cls) -> str | None:  # pragma: no cover - 子类必须覆盖
        raise NotImplementedError

    @classmethod
    def _skip_reason(cls) -> str | None:
        if not hasattr(cls, "_cached_skip_reason"):
            cls._cached_skip_reason = cls._ready_probe()
        return cls._cached_skip_reason

    def _check_ready(self) -> None:
        reason = type(self)._skip_reason()
        if reason:
            self.skipTest(reason)


# ================================================================ 基线守卫
class TestWWBaselineGuards(unittest.TestCase):
    """WW 扩充前后的回归守卫（WW-T07 的单元/集成层证据之一）。

    这些用例在当前基线（P 表 142 位 attested）即应 PASS；WW 合入后继续
    保证旧功能零漂移。任何一条 FAIL 都属于实现回归，与 WW 新增功能无关。
    """

    @classmethod
    def setUpClass(cls):
        cls.catalog = build_catalog(20261120)
        cls.pt = _load_json(PTABLE_JSON)
        cls.stats = cls.pt["stats"]

    def test_baseline_p_table_142_anchor(self):
        """P 表处于基线阶段时，stats 必须与 attested 基线逐字段一致（WW-T05-④ 的基线面）。"""
        records = self.stats["records"]
        self.assertIn(
            records,
            (BASELINE_PT_RECORDS, WW_PT_RECORDS),
            "P 表 records=%d 处于非法中间态（既非基线 142 也非目标 192）" % records,
        )
        if records == BASELINE_PT_RECORDS:
            for key, expected in BASELINE_PT_STATS.items():
                self.assertEqual(
                    self.stats.get(key), expected, "基线字段 %s 漂移（期望 %s）" % (key, expected)
                )
            self.assertEqual(
                self.stats.get("by_asset_type"), BASELINE_PT_BY_TYPE, "基线分类计数漂移"
            )

    def test_baseline_floors_and_targets(self):
        """基线三层（-1/0/1）仍存在；WW 新增楼层只许追加，不许改写旧层。"""
        for floor in BASELINE_FLOORS:
            self.assertIn(floor, self.catalog.room_targets, "基线楼层 %r 丢失" % floor)
            templates = [t for t in self.catalog.room_templates.values() if t.floor == floor]
            self.assertTrue(templates, "基线楼层 %r 无任何房间模板" % floor)

    def test_baseline_haunt_selection_1_to_70(self):
        """剧本选择函数对 1–70 的覆盖不因 WW 追加而漂移（WW-T02 的旧剧本回归面）。"""
        selected = {
            GameEngine(seed=h)._select_haunt_id("room_%d" % h, "omen_%d" % h)
            for h in range(500)
        }
        self.assertTrue(
            set(BASELINE_HAUNT_SLOTS) <= selected,
            "1–70 选择覆盖缺口：%s" % sorted(set(BASELINE_HAUNT_SLOTS) - selected),
        )
        self.assertTrue(
            selected <= set(BASELINE_HAUNT_SLOTS) | set(WW_HAUNT_SLOTS),
            "选择函数返回了非法槽位：%s"
            % sorted(selected - set(BASELINE_HAUNT_SLOTS) - set(WW_HAUNT_SLOTS)),
        )

    def test_baseline_card_collections_anchors(self):
        """三卡集合计数不小于基线且 kind 字段合法（WW 扩卡时只许追加）。"""
        for cards, kind in ((EVENT_BASES, "event"), (ITEM_CARDS, "item"), (OMEN_CARDS, "omen")):
            self.assertGreaterEqual(
                len(cards), BASELINE_CONTENT_COUNTS[kind], "%s 集合计数低于基线" % kind
            )
            bad = [c.get("card_id") for c in cards if c.get("kind") != kind]
            self.assertEqual(bad, [], "%s 集合存在 kind 错误的卡：%s" % (kind, bad[:8]))

    def test_baseline_effect_ids_fully_resolved(self):
        """基线 81 个非 generic effect_id 全范围源码解析 0 unknown（WW-T03-② 的基线面）。"""
        unknown = _unknown_effect_ids(_all_cards(), include_rooms=True)
        self.assertEqual(unknown, [], "存在引擎/剧本/AI 全范围源码均未解析的 effect_id：%s" % unknown)


# ================================================================ WW-T01
class TestWWT01RoofExploration(_WWReadyMixin, unittest.TestCase):
    """WW-T01（P0）：屋顶层探索放置正确。

    判据（验收 §3）：① 命中屋顶层探索时新房间 100% 取自屋顶房池，不出现
    基础版房间；② 放置后房间 floor==屋顶层值；③ 同局屋顶房间不重复
    （≤房池大小且唯一）；④ 首次屋顶探索后屋顶房间数 ≥1；⑤ ≥50 个随机
    种子遍历 0 异常 0 traceback。
    """

    @classmethod
    def _ready_probe(cls) -> str | None:
        catalog = build_catalog(20261120)
        roof_floor, pool, note = _detect_roof(catalog)
        cls._roof_floor = roof_floor
        cls._pool = pool
        if roof_floor is None:
            return (
                "WW-T01 SKIP：屋顶层引擎未就绪（%s）。架构接口 FLOOR_ROOF/ROOF_ROOMS "
                "与 room_targets 键域扩展均未落地，待实现分支合入后重跑。" % note
            )
        return None

    def test_t01_roof_pool_pure_and_bounded(self):
        """①② 房池纯净：floor 归属屋顶层、不与基础版模板重叠、效果有归属、池数对齐判据 20。"""
        self._check_ready()
        base_ids = {
            t.id for t in build_catalog(20261120).room_templates.values() if t.floor in BASELINE_FLOORS
        }
        overlap = sorted(set(self._pool) & base_ids)
        self.assertEqual(overlap, [], "屋顶房池混入基础版房间：%s" % overlap)
        for tid, tpl in self._pool.items():
            self.assertEqual(tpl.floor, self._roof_floor, "模板 %s floor=%r 非屋顶层" % (tid, tpl.floor))
        unknown = _unknown_effect_ids([{"effect_id": t.effect_id} for t in self._pool.values()])
        self.assertEqual(
            unknown,
            [],
            "屋顶房间 effect_id 全范围源码未解析：%s（房间效果须挂在 _apply_room_effect 或剧本层）" % unknown,
        )
        # 口径裁决断言：验收标准写明"20 个屋顶房池"。
        # 官方清单 floors_possible 含 roof 的房间为 11 个（20 块板块中 11 块主面
        # 为 roof），差异已在 docs/qa_widows_walk.md §R2 登记待裁决。
        self.assertEqual(
            len(self._pool),
            20,
            "屋顶房池数量=%d ≠ 验收判据 20（实测 %s）。若实现按官方 11 个 roof 主面房间"
            "建模，属 §R2 口径冲突，须由验收评审裁决而非静默放行" % (len(self._pool), sorted(self._pool)[:8]),
        )

    def test_t01_seeded_roof_exploration_placement(self):
        """③④⑤ 50 种子遍历：每次抽牌必属屋顶房池、同局唯一、首次探索后 ≥1、0 异常。"""
        self._check_ready()
        catalog = build_catalog(20261120)
        base_ids = {t.id for t in catalog.room_templates.values() if t.floor in BASELINE_FLOORS}
        for seed in WW_T01_SEEDS:
            with self.subTest(seed=seed):
                engine = _new_game(seed)
                drawn: list[str] = []
                # 模拟屋顶探索放置：反复抽取 + 网格放置，等价于探索翻门出房的
                # 数据面（完整 move_player E2E 由验收脚本与独立验收覆盖）。
                while engine.has_remaining_room_cards(self._roof_floor):
                    template = engine._draw_room_template(self._roof_floor)
                    if template is None:
                        break
                    self.assertEqual(
                        template.floor,
                        self._roof_floor,
                        "seed=%d 抽到非屋顶层模板 %s" % (seed, template.id),
                    )
                    self.assertIn(template.id, self._pool, "seed=%d 抽到房池外模板 %s" % (seed, template.id))
                    self.assertNotIn(template.id, base_ids, "seed=%d 抽到基础版房间 %s" % (seed, template.id))
                    drawn.append(template.id)
                    engine._place_room(template, 100 + len(drawn) * 3, 100, 0)
                self.assertTrue(drawn, "seed=%d 首次屋顶探索未放置任何房间" % seed)
                self.assertEqual(len(drawn), len(set(drawn)), "seed=%d 屋顶房间重复：%s" % (seed, drawn))
                self.assertLessEqual(len(drawn), len(self._pool), "seed=%d 屋顶放置超过房池" % seed)
                roof_on_board = {
                    r.template_id
                    for r in engine.state.board.values()
                    if r.floor == self._roof_floor
                }
                self.assertEqual(set(drawn), roof_on_board, "seed=%d 牌堆与棋盘屋顶房间不一致" % seed)

    def test_t01_roof_pool_official_alignment(self):
        """官方清单对齐：屋顶房池与 ww_official_content.json 20 房间（roof 可放子集）一致。"""
        self._check_ready()
        official = _load_official_ww()
        if official is None:
            self.skipTest("官方清单 ww_official_content.json 不可读，官方对齐检查 not-run")
        official_ids = {r["id"] for r in official["rooms"]}
        official_names = {r["name_en"].lower() for r in official["rooms"]}
        official_roof = {
            r["id"] for r in official["rooms"] if "roof" in (r.get("floors_possible") or [])
        }
        matched_ids = set(self._pool) & official_ids
        matched_names = {
            tid
            for tid, t in self._pool.items()
            if (t.source_name or "").lower() in official_names
        }
        matched = matched_ids | matched_names
        self.assertTrue(
            matched,
            "屋顶房池与官方 20 房间清单零交集（id 或 source_name 均未对齐）；官方 roof 可放房间=%d"
            % len(official_roof),
        )
        official_id_by_name = {r["name_en"].lower(): r["id"] for r in official["rooms"]}
        resolved = set(matched_ids)
        for tid, t in self._pool.items():
            by_name = official_id_by_name.get((t.source_name or "").lower())
            if by_name:
                resolved.add(by_name)
        unmatched_official = sorted(official_roof - resolved)
        self.assertEqual(
            unmatched_official,
            [],
            "官方 roof 楼层房间未全部进入屋顶房池：%s" % unmatched_official,
        )


# ================================================================ WW-T02
class TestWWT02HauntSlots71to120(_WWReadyMixin, unittest.TestCase):
    """WW-T02（P0）：剧本 71–120 全部可触发。

    判据（验收 §3）：① audit_haunts.py 120/120（双语）为验收脚本执行项，
    不在本文件（见 docs/qa_widows_walk.md §执行矩阵）；② haunt_rules 对
    50 本新剧本逐一选择成功且与冻结清单 ID 一一对应；③ 每本模块可 import、
    入口存在、含叛徒/英雄胜负条件字段；④ 任选 ≥10 本实际进入作祟流程 0 异常。
    """

    @classmethod
    def _ready_probe(cls) -> str | None:
        seen, note = _ww_haunt_slots()
        cls._seen = seen
        cls._note = note
        if not seen:
            return (
                "WW-T02 SKIP：剧本槽位 71–120 全部未就绪（%s）。官方编号 51–100 的 50 本 "
                "haunt 模块与 HAUNT_RULE_OVERRIDES/haunts/ 目录均无踪迹。" % note
            )
        return None

    def test_t02_haunt_modules_importable_with_win_conditions(self):
        """③ 每本 haunt_<slot> 模块可 import、含 GenericModeHandler 子类入口、
        rule_data 含 hero_goal/traitor_goal 胜负条件字段。"""
        self._check_ready()
        from haunts.base import GenericModeHandler

        rules = haunt_rules.HAUNT_RULE_OVERRIDES
        failures: list[str] = []
        for slot in WW_HAUNT_SLOTS:
            files = list((GAME_DIR / "haunts").glob("haunt_%d_*.py" % slot))
            if not files:
                failures.append("槽位 %d：haunts/haunt_%d_*.py 缺失" % (slot, slot))
                continue
            module_name = "haunts." + files[0].stem
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                failures.append("槽位 %d：import %s 失败 %r" % (slot, module_name, exc))
                continue
            handlers = [
                obj
                for obj in vars(module).values()
                if isinstance(obj, type)
                and issubclass(obj, GenericModeHandler)
                and obj is not GenericModeHandler
            ]
            if not handlers:
                failures.append("槽位 %d：模块内无 GenericModeHandler 子类入口" % slot)
            rule = rules.get(slot)
            if not rule:
                failures.append("槽位 %d：HAUNT_RULE_OVERRIDES 无规则数据" % slot)
                continue
            for field in ("hero_goal", "traitor_goal"):
                if not rule.get(field):
                    failures.append("槽位 %d：rule_data 缺胜负条件字段 %s" % (slot, field))
        self.assertEqual(
            failures,
            [],
            "剧本 71–120 模块审计 %d 项缺口：%s" % (len(failures), failures[:10]),
        )

    def test_t02_selection_covers_slots_71_120(self):
        """② 选择函数覆盖全部 50 个新槽位（房间×预兆组合枚举法，同 verify_v1 口径）。"""
        self._check_ready()
        selected: set[int] = set()
        for h in range(720):
            selected.add(GameEngine(seed=h)._select_haunt_id("room_%d" % h, "omen_%d" % h))
        gaps = [s for s in WW_HAUNT_SLOTS if s not in selected]
        self.assertEqual(
            gaps,
            [],
            "720 组合枚举无法选到剧本槽位：%s（选择映射未接入 71–120）" % gaps,
        )

    def test_t02_trigger_combinations_map_to_official_ids(self):
        """② 官方触发组合语义对齐：冻结清单 trigger（rooms×omens）映射到实现 id 后
        逐一选择，返回槽位与官方映射（slot = official_id + 20）一致。"""
        self._check_ready()
        official = _load_official_ww()
        if official is None:
            self.skipTest("官方清单 ww_official_content.json 不可读，触发组合对齐 not-run")
        catalog = build_catalog(20261120)
        room_index: dict[str, str] = {}
        for tpl in catalog.room_templates.values():
            if tpl.source_name:
                room_index.setdefault(tpl.source_name.lower(), tpl.id)
        card_index: dict[str, str] = {}
        for card in _all_cards():
            if card.get("source_name"):
                card_index.setdefault(card["source_name"].lower(), card["card_id"])
        official_slots = {h["id"] for h in official["haunts"]}
        self.assertEqual(
            official_slots,
            set(WW_HAUNT_SLOTS) | {"mega"},
            "官方清单剧本槽位与 71–120 映射不符：%s" % sorted(official_slots - {"mega"}),
        )
        unmatched_rooms: set[str] = set()
        unmatched_omens: set[str] = set()
        wrong: list[str] = []
        mapped = 0
        for haunt in official["haunts"]:
            slot = haunt["id"]
            if slot == "mega" or slot not in WW_HAUNT_SLOTS:
                continue
            rooms = [room_index.get(n.lower()) for n in haunt["trigger"].get("rooms", [])]
            omens = [card_index.get(n.lower()) for n in haunt["trigger"].get("omens", [])]
            room_ids = [r for r in rooms if r]
            omen_ids = [o for o in omens if o]
            for name, hit in zip(haunt["trigger"].get("rooms", []), rooms):
                if not hit:
                    unmatched_rooms.add(name)
            for name, hit in zip(haunt["trigger"].get("omens", []), omens):
                if not hit:
                    unmatched_omens.add(name)
            if not room_ids or not omen_ids:
                continue
            mapped += 1
            chosen = GameEngine(seed=slot)._select_haunt_id(room_ids[0], omen_ids[0])
            if chosen != slot:
                wrong.append(
                    "槽位 %d（官方 %s《%s》）触发组合 %s+%s 选到 %r"
                    % (slot, haunt["official_id"], haunt["name_en"], room_ids[0], omen_ids[0], chosen)
                )
        self.assertEqual(
            wrong,
            [],
            "官方触发组合选择映射错误 %d 项：%s" % (len(wrong), wrong[:10]),
        )
        self.assertEqual(
            sorted(unmatched_rooms),
            [],
            "官方触发房间未实现（source_name 无法映射）：%s" % sorted(unmatched_rooms),
        )
        self.assertEqual(
            sorted(unmatched_omens),
            [],
            "官方触发预兆未实现（source_name 无法映射）：%s" % sorted(unmatched_omens),
        )
        self.assertGreaterEqual(mapped, 40, "仅 %d/50 本官方触发组合可完整映射" % mapped)

    def test_t02_haunt_flow_smoke_10_scenarios(self):
        """④ 任选 ≥10 本实际进入作祟流程 0 异常（haunt_playtest.run_case 内存对局）。"""
        self._check_ready()
        slots = self._seen[:10]
        if len(slots) < 10:
            self.skipTest("WW 槽位仅 %d/50 已见（%s），冒烟样例不足 10 本" % (len(slots), self._note))
        import haunt_playtest

        errors: list[str] = []
        finished = 0
        for slot in slots:
            try:
                result = haunt_playtest.run_case(
                    haunt_id=slot, seed=7100 + slot, players=4, max_turns=80
                )
            except Exception as exc:  # noqa: BLE001 - 冒烟语义：任何异常都计入
                errors.append("槽位 %d：%r" % (slot, exc))
                continue
            if not isinstance(result, dict) or "winner" not in result:
                errors.append("槽位 %d：run_case 返回缺 winner 键 %r" % (slot, result))
            else:
                finished += 1
        self.assertEqual(errors, [], "作祟流程冒烟异常 %d 项：%s" % (len(errors), errors[:6]))
        self.assertEqual(finished, 10, "冒烟完成 %d/10" % finished)


# ================================================================ WW-T03
class TestWWT03NewCards(_WWReadyMixin, unittest.TestCase):
    """WW-T03（P0）：新卡牌效果函数可执行。

    判据（验收 §3）：① 冻结清单内每张新卡有 effect_id；② 引擎解析未知
    effect_id 计 0；③ 全量新卡效果执行（正常+边界入参）0 error 0 traceback
    ——真实对局执行由 WW-T02 冒烟与验收脚本覆盖，本文件断言 effect_id 全
    范围源码解析 + 描述文本覆盖；④ content 集合计数与 P 表分类计数一致
    （event 60 / item 32 / omen 18）。
    """

    @classmethod
    def _ready_probe(cls) -> str | None:
        counts = {"event": len(EVENT_BASES), "item": len(ITEM_CARDS), "omen": len(OMEN_CARDS)}
        gaps = {k: WW_CARD_TARGETS[k] - v for k, v in counts.items() if v < WW_CARD_TARGETS[k]}
        cls._counts = counts
        if gaps:
            return (
                "WW-T03 SKIP：卡牌集合未达冻结目标（实测 event=%d/item=%d/omen=%d，目标 %s，"
                "缺口 %s）。注：基线 EVENT_BASES=11 与 P 表 card_event=45 口径分裂见 "
                "docs/qa_widows_walk.md §R3。" % (
                    counts["event"], counts["item"], counts["omen"], WW_CARD_TARGETS, gaps
                )
            )
        return None

    def test_t03_card_counts_reach_freeze_targets(self):
        """④ content 集合计数达冻结目标。"""
        self._check_ready()
        for kind, target in WW_CARD_TARGETS.items():
            self.assertEqual(
                self._counts[kind], target, "%s 集合计数 %d ≠ 冻结目标 %d" % (kind, self._counts[kind], target)
            )

    def test_t03_content_counts_match_p_table(self):
        """④ content 集合计数与 P 表分类计数一致（event 60 / item 32 / omen 18）。"""
        self._check_ready()
        pt = _load_json(PTABLE_JSON)
        by_type = pt["stats"]["by_asset_type"]
        pairs = (
            ("card_event", "event", EVENT_BASES),
            ("card_item", "item", ITEM_CARDS),
            ("card_omen", "omen", OMEN_CARDS),
        )
        for pt_key, kind, cards in pairs:
            self.assertEqual(
                len(cards),
                by_type.get(pt_key),
                "%s：content 集合 %d 与 P 表 %s=%r 不一致"
                % (kind, len(cards), pt_key, by_type.get(pt_key)),
            )

    def test_t03_all_card_effect_ids_resolvable(self):
        """①② 每张卡有非 generic effect_id 且全范围源码解析 0 unknown。"""
        self._check_ready()
        for card in _all_cards():
            self.assertTrue(
                card.get("effect_id") not in (None, "", "none"),
                "卡 %s 缺 effect_id" % card.get("card_id"),
            )
        unknown = _unknown_effect_ids(_all_cards())
        self.assertEqual(
            unknown,
            [],
            "引擎/剧本/AI/help_text 全范围源码未解析的新卡 effect_id：%s" % unknown,
        )

    def test_t03_card_descriptions_covered(self):
        """③ 的静态面：全部卡牌在 help_text 有可读描述（效果入口可执行的最低证据）。"""
        self._check_ready()
        import help_text

        missing: list[str] = []
        for card in _all_cards():
            try:
                short = help_text.card_short(card["card_id"])
                usage = help_text.card_usage(card["card_id"])
            except Exception as exc:  # noqa: BLE001
                missing.append("%s：描述函数异常 %r" % (card["card_id"], exc))
                continue
            if not (short or usage or card.get("text")):
                missing.append(card["card_id"])
        self.assertEqual(missing, [], "无任何可读描述的新卡：%s" % missing[:10])


# ================================================================ WW-T04
class TestWWT04RoofFull(_WWReadyMixin, unittest.TestCase):
    """WW-T04（P0）：屋顶层满时不再放置。

    判据（验收 §3）：① 置满屋顶（验收口径 20/20）后再触发屋顶探索 → 不放置
    新房间、不重复既有房间；② 游戏状态不进入异常分支，返回/日志明确表达
    "屋顶层已满"（引擎数据面表达：_draw_room_template 返回 None +
    has_remaining_room_cards=False；UI 文案归 WW-T09）；③ 0 traceback；
    ④ 其余三层探索不受影响。
    """

    @classmethod
    def _ready_probe(cls) -> str | None:
        catalog = build_catalog(20261120)
        roof_floor, pool, note = _detect_roof(catalog)
        cls._roof_floor = roof_floor
        cls._pool = pool
        if roof_floor is None:
            return "WW-T04 SKIP：屋顶层引擎未就绪（%s）" % note
        return None

    def _full_roof_engine(self) -> GameEngine:
        engine = _new_game(20261120)
        for index, (tid, tpl) in enumerate(sorted(self._pool.items())):
            engine._place_room(tpl, 200 + index * 3, 200, 0)
        return engine

    def test_t04_roof_pool_exhaustion_no_replacement(self):
        """①②③ 房池耗尽后：draw 返回 None、无重复放置、0 异常、房池数量对齐验收口径 20。"""
        self._check_ready()
        engine = self._full_roof_engine()
        self.assertFalse(
            engine.has_remaining_room_cards(self._roof_floor),
            "屋顶房池 %d 项全部放置后仍有剩余房间牌" % len(self._pool),
        )
        for _ in range(5):  # 连续触发屋顶探索，均须拒绝
            self.assertIsNone(
                engine._draw_room_template(self._roof_floor),
                "屋顶层已满时仍返回了新房间模板（未明确表达已满）",
            )
        roof_on_board = {
            r.template_id
            for r in engine.state.board.values()
            if r.floor == self._roof_floor
        }
        self.assertEqual(roof_on_board, set(self._pool), "棋盘屋顶房间集合与房池不一致")
        self.assertEqual(len(roof_on_board), len(self._pool), "屋顶房间重复放置")
        # 口径裁决断言：验收判据"置满屋顶（20/20）"。
        self.assertEqual(
            len(self._pool),
            20,
            "屋顶房池数量=%d ≠ 验收判据 20（docs/qa_widows_walk.md §R2 口径冲突待裁决）"
            % len(self._pool),
        )

    def test_t04_other_floors_unaffected(self):
        """④ 屋顶满后其余三层仍有房间牌可探索，且跨层 draw 不串层。"""
        self._check_ready()
        engine = self._full_roof_engine()
        for floor in sorted(BASELINE_FLOORS):
            self.assertTrue(
                engine.has_remaining_room_cards(floor),
                "屋顶满后基线楼层 %r 的房间牌受影响（应为满池）" % floor,
            )
            template = engine._draw_room_template(floor)
            self.assertIsNotNone(template, "屋顶满后基线楼层 %r 探索被拒" % floor)
            self.assertEqual(
                template.floor, floor, "基线楼层 %r 抽到了 %r 层模板" % (floor, template.floor)
            )
            self.assertNotIn(template.id, self._pool, "基线层抽到屋顶房池模板（串层）")


# ================================================================ WW-T05
class TestWWT05PTable192(_WWReadyMixin, unittest.TestCase):
    """WW-T05（P1）：P 表 192 位分类计数正确。

    判据（验收 §3）：① records=192；room 70 / character 12 / card_event 60 /
    card_item 32 / card_omen 18；② missing=0 / corrupted=0 / duplicate=0 /
    placeholder=0 / fallback=0；③ usable=192 / partial=0；④ 旧 142 行
    record_id/target_ref/runtime_key/availability 语义与基线逐字段一致；
    ⑤ 新增 50 行 ID 唯一。基线阶段（records=142，attested）整类 SKIP。
    """

    @classmethod
    def _ready_probe(cls) -> str | None:
        pt = _load_json(PTABLE_JSON)
        cls._pt = pt
        cls._stats = pt["stats"]
        cls._records = pt["records"]
        cls._ids = [r["record_id"] for r in cls._records if isinstance(r, dict)]
        records = cls._stats["records"]
        if records == BASELINE_PT_RECORDS:
            return (
                "WW-T05 SKIP：P 表仍处基线阶段（records=142，attested 基线），192 位扩展未"
                "落地；全部目标断言待实现分支合入后重跑。基线锚点由 TestWWBaselineGuards"
                ".test_baseline_p_table_142_anchor 守护。"
            )
        if records != WW_PT_RECORDS:
            raise AssertionError(
                "P 表 records=%d 处于非法中间态（既非基线 142 也非目标 192）" % records
            )
        return None

    def test_t05_records_192_with_category_counts(self):
        """① 总量与分类计数（硬指标）。"""
        self._check_ready()
        self.assertEqual(self._stats["records"], WW_PT_RECORDS, "records ≠ 192")
        self.assertEqual(
            self._stats.get("by_asset_type"),
            WW_PT_BY_TYPE,
            "分类计数漂移：%r ≠ %r" % (self._stats.get("by_asset_type"), WW_PT_BY_TYPE),
        )

    def test_t05_availability_targets(self):
        """②③ 可用性状态收口期望。"""
        self._check_ready()
        for key, expected in WW_PT_STATS.items():
            self.assertEqual(
                self._stats.get(key),
                expected,
                "可用性字段 %s=%r ≠ %s" % (key, self._stats.get(key), expected),
            )

    def test_t05_new_record_ids_unique_and_old_preserved(self):
        """⑤ record_id 全局唯一，无重复无空值。"""
        self._check_ready()
        self.assertEqual(len(self._ids), WW_PT_RECORDS, "records 明细行数 ≠ 192")
        blanks = [i for i in self._ids if not i]
        self.assertEqual(blanks, [], "存在空 record_id")
        dupes = sorted({i for i in self._ids if self._ids.count(i) > 1})
        self.assertEqual(dupes, [], "record_id 重复：%s" % dupes[:8])

    def test_t05_baseline_zero_drift_vs_snapshot(self):
        """④ 旧 142 行零漂移：与基线快照逐 record_id 对比（快照由验收执行脚本导出）。"""
        self._check_ready()
        if not BASELINE_IDS_SNAPSHOT.exists():
            self.skipTest(
                "零漂移对比 not-run：基线快照 %s 缺失（由验收执行脚本在扩表前导出 142 个 "
                "record_id；缺失项不折算 PASS，计入验收报告 not_run）" % BASELINE_IDS_SNAPSHOT.name
            )
        baseline_ids = _load_json(BASELINE_IDS_SNAPSHOT)
        self.assertEqual(len(baseline_ids), BASELINE_PT_RECORDS, "基线快照行数 ≠ 142")
        missing = sorted(set(baseline_ids) - set(self._ids))
        self.assertEqual(missing, [], "旧 142 行 record_id 在新 P 表中缺失：%s" % missing[:10])
        self.assertEqual(
            len(self._ids) - len(set(baseline_ids) & set(self._ids)),
            50,
            "新增行数 ≠ 50",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
