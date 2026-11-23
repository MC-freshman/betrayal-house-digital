#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P 表执行与 UI 绑定的功能 / 边界 / 异常 / 回归测试（unittest，标准库 + Pillow）。

覆盖范围
--------
* 结构：274 行、分类 12/50/45/22/13、0/95/47/0/0、33 列（含 runtime_key）、发布档 7 列取值；
* 产物：95 个源文件、98 个运行时 PNG、路径逐段大小写、运行时尺寸；
* 注册表：274 个 target_ref/runtime_key/record_id/content_ref 全解析、未知键 None、重复键拒绝、
  BOM 清单可读、含 ``../`` 的键被拒；
* 异常：0 字节 PNG、截断 PNG、坏 JSON、运行时文件缺失、清单缺 records；
* 回归：两次加载一致、两次构建逐字节一致（generated_at 除外）；
* UI：Tk withdraw 后加载房间图与卡牌，校验尺寸与缓存命中；无 tkinter 时
  明确 FAIL（不使用 skip 冒充通过）。

跑法::

    python -m unittest qa.test_p_table_execution -v
    python qa/test_p_table_execution.py

测试只读 photos/，只写 qa/fixtures 与临时目录；重新构建 P 表时会写 assets/。
"""

from __future__ import annotations

import contextlib
import copy
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

GAME_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GAME_DIR.parents[2]
QA_DIR = Path(__file__).resolve().parent
FIXTURES = QA_DIR / "fixtures"
ASSETS = GAME_DIR / "assets"
PTABLE_JSON = ASSETS / "p_table.json"
PTABLE_CSV = ASSETS / "p_table.csv"
MAPPING_JSON = ASSETS / "asset_mapping.json"
INVENTORY_JSON = PROJECT_ROOT / ".codebuddy" / "wfat" / "photos_inventory.json"

if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

import asset_pipeline  # noqa: E402
import asset_registry  # noqa: E402
import ui_asset_binding  # noqa: E402
from asset_registry import AssetRegistry, png_size  # noqa: E402

EXPECTED_TOTAL = 274
EXPECTED_BY_TYPE = {
    "character": 12,
    "room": 50,
    "card_event": 45,
    "card_item": 22,
    "card_omen": 13,
    # run6 六类渲染面：274 = 142 + 132
    "monster": 52,
    "haunt": 70,
    "ending": 2,
    "card_back": 3,
    "room_back": 2,
    "dice": 3,
}
# run5 v2：47 位登记 + 130 张 JPEG 无损转码后，274 位全部 usable。
# 旧 0/95/47 已退役（见 qa/run5_baseline_diff.json），断言不删、只改期望值。
EXPECTED_AVAILABILITY = {
    "usable": 274,
    "partial": 0,
    "missing": 0,
    "corrupted": 0,
    "duplicate": 0,
}
RUNTIME_SIZE = {
    "character": (320, 320),
    "room": (512, 512),
    "card_omen": (480, 672),
    "card_item": (480, 672),
    "card_event": (480, 672),
    # run6 六类渲染面：尺寸取 P 表 runtime_specs（工程自定，见 asset_pipeline.RUNTIME_SPECS）
    "monster": (512, 512),
    "haunt": (1280, 720),
    "ending": (1024, 576),
    "card_back": (480, 640),
    "room_back": (512, 512),
    "dice": (256, 256),
}
CATEGORY_DIR = {
    "character": "char",
    "room": "room",
    "card_omen": "omen",
    "card_item": "item",
    "card_event": "event",
    # run6 六类渲染面的 category_dir 与 FAMILIES.dir 同名
    "monster": "monster",
    "haunt": "haunt",
    "ending": "ending",
    "card_back": "card_back",
    "room_back": "room_back",
    "dice": "dice",
}
# 需要 alpha 的类别（asset_pipeline.ALPHA_REQUIRED）：角色 + 三类贴图型渲染面
ALPHA_REQUIRED_TYPES = {"character", "monster", "room_back", "dice"}
RELEASE_COLUMNS = [
    "bytes",
    "sha256",
    "category_dir",
    "alpha_required",
    "canonical_record_id",
    "reviewer",
    "verified_at",
]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
VERIFIED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_GENERATION_SNAPSHOT = {}


# ----------------------------------------------------------------------
# 公共工具
# ----------------------------------------------------------------------
def run_ptable_stage():
    """在进程内重建 P 表（只写 assets/，不碰 photos/）。"""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = asset_pipeline.main(["--stage", "ptable"])
    if code != 0:
        raise AssertionError("asset_pipeline --stage ptable 返回 %s\n%s" % (code, buffer.getvalue()))
    return buffer.getvalue()


def read_csv():
    with PTABLE_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def read_json():
    with PTABLE_JSON.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def norm(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    return str(value)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def case_consistent(rel_path: str) -> bool:
    """逐段比对磁盘真实名称（Windows 大小写不敏感，发布端敏感）。"""
    current = PROJECT_ROOT
    for part in rel_path.split("/"):
        if not part:
            continue
        try:
            names = {entry.name for entry in current.iterdir()}
        except OSError:
            return False
        if part not in names:
            return False
        current = current / part
    return True


def first_row(asset_type=None, availability=None, exclude_availability=None):
    """按类别/可用性取第一行；exclude_availability 用于排除缺失行。"""
    _, rows = read_csv()
    for row in rows:
        if asset_type and row["asset_type"] != asset_type:
            continue
        if availability and row["availability"] != availability:
            continue
        if exclude_availability and row["availability"] == exclude_availability:
            continue
        return row
    raise AssertionError("找不到符合条件的行：%s / %s / exclude=%s"
                         % (asset_type, availability, exclude_availability))


def first_json_row(payload, asset_type):
    """从已加载的 P 表 JSON 里取第一条指定类别的记录（合成样本的基底）。"""
    for row in payload.get("records") or []:
        if row.get("asset_type") == asset_type:
            return row
    raise AssertionError("JSON 中找不到 %s 行" % asset_type)


def load_registry():
    return AssetRegistry.load(PTABLE_JSON, base_dir=str(PROJECT_ROOT))


def setUpModule():
    if not FIXTURES.is_dir():
        raise RuntimeError("qa/fixtures 缺失，请先运行 python qa/make_fixtures.py")
    header, _ = read_csv()
    if header != list(asset_pipeline.CSV_COLUMNS):
        run_ptable_stage()
    # 冻结一次构建结果，供“两次生成一致”用例做对照
    _GENERATION_SNAPSHOT["csv"] = PTABLE_CSV.read_bytes()
    _GENERATION_SNAPSHOT["json"] = read_json()


# ----------------------------------------------------------------------
# 1. 结构
# ----------------------------------------------------------------------
class TestPTableStructure(unittest.TestCase):
    def test_01_csv_header_has_33_columns(self):
        header, rows = read_csv()
        self.assertEqual(len(header), 33, "CSV 应为 33 列（26 业务列含 runtime_key + 7 发布列）")
        self.assertEqual(header, list(asset_pipeline.CSV_COLUMNS))
        for column in RELEASE_COLUMNS:
            self.assertIn(column, header)
        # 新旧键同表并存：target_ref 是规范溯源键，runtime_key 是运行时键
        self.assertIn("target_ref", header)
        self.assertIn("runtime_key", header)
        self.assertEqual(len(rows), EXPECTED_TOTAL)

    def test_02_json_records_have_same_fields(self):
        header, rows = read_csv()
        payload = read_json()
        records = payload["records"]
        self.assertEqual(len(records), EXPECTED_TOTAL)
        self.assertEqual(list(payload["schema"]["columns"]), header)
        for index, (csv_row, json_row) in enumerate(zip(rows, records)):
            self.assertEqual(set(json_row), set(header), "第 %d 行字段集不一致" % index)
            for column in header:
                self.assertEqual(norm(csv_row[column]), norm(json_row[column]),
                                 "第 %d 行 %s 列 CSV/JSON 不一致" % (index, column))

    def test_03_counts_match_stats(self):
        _, rows = read_csv()
        stats = read_json()["stats"]
        self.assertEqual(len(rows), EXPECTED_TOTAL)
        counts = {}
        for row in rows:
            counts[row["asset_type"]] = counts.get(row["asset_type"], 0) + 1
        self.assertEqual(counts, EXPECTED_BY_TYPE)
        self.assertEqual(stats["records"], EXPECTED_TOTAL)
        for key, value in EXPECTED_AVAILABILITY.items():
            self.assertEqual(stats[key], value)
        availability = {}
        for row in rows:
            availability[row["availability"]] = availability.get(row["availability"], 0) + 1
        for key, value in EXPECTED_AVAILABILITY.items():
            self.assertEqual(availability.get(key, 0), value, key)
        self.assertEqual(len({row["record_id"] for row in rows}), EXPECTED_TOTAL)
        self.assertEqual(len({row["target_ref"] for row in rows}), EXPECTED_TOTAL)

    def test_04_missing_rows_are_split_and_documented(self):
        # run5 v2：0 个缺口。断言不删除——改为"任何 missing 即失败"，
        # 并核对 274 行全部有源文件、missing_note 为空、无回退残留。
        _, rows = read_csv()
        missing = [row for row in rows if row["availability"] == "missing"]
        self.assertEqual(len(missing), 0, [row["record_id"] for row in missing[:5]])
        fallback = [row for row in rows if row["mapping_status"] == "fallback"]
        pending = [row for row in rows if row["mapping_status"] == "pending_missing"]
        self.assertEqual((len(fallback), len(pending)), (0, 0))
        for row in rows:
            self.assertTrue(row["source_path"], row["record_id"])
            self.assertEqual(row["missing_note"], "", row["record_id"])
            self.assertEqual(row["fallback_ref"], "", row["record_id"])
            self.assertEqual(row["runtime_status"], "ok", row["record_id"])
            self.assertEqual(row["mapping_status"], "matched", row["record_id"])

    def test_05_release_columns_values(self):
        _, rows = read_csv()
        expected_verified = asset_pipeline.verification_date()
        ids = {row["record_id"] for row in rows}
        for row in rows:
            record_id = row["record_id"]
            self.assertEqual(row["reviewer"], "automated", record_id)
            self.assertTrue(VERIFIED_AT_RE.match(row["verified_at"]), record_id)
            self.assertEqual(row["verified_at"], expected_verified, record_id)
            self.assertEqual(row["category_dir"], CATEGORY_DIR[row["asset_type"]], record_id)
            expected_alpha = (
                "true" if row["asset_type"] in ALPHA_REQUIRED_TYPES else "false")
            self.assertEqual(row["alpha_required"], expected_alpha, record_id)
            self.assertIn(row["canonical_record_id"], ids, record_id)
            self.assertEqual(row["canonical_record_id"], record_id, record_id)

    def test_06_release_sha256_and_bytes_come_from_source(self):
        _, rows = read_csv()
        checked = 0
        for row in rows:
            if row["availability"] == "missing":
                self.assertEqual(row["bytes"], "", row["record_id"])
                self.assertEqual(row["sha256"], "", row["record_id"])
                continue
            source = PROJECT_ROOT / row["source_path"]
            self.assertTrue(source.is_file(), row["source_path"])
            self.assertEqual(row["bytes"], str(source.stat().st_size), row["record_id"])
            self.assertRegex(row["sha256"], SHA256_RE)
            self.assertEqual(row["sha256"], sha256_of(source), row["record_id"])
            # run5 v2：源文件必须是真 PNG（扩展名与魔数一致）
            self.assertEqual(source.suffix.lower(), ".png", row["record_id"])
            self.assertEqual(source.read_bytes()[:8], PNG_SIGNATURE, row["record_id"])
            checked += 1
        self.assertEqual(checked, 274)


# ----------------------------------------------------------------------
# 2. 运行时产物
# ----------------------------------------------------------------------
class TestRuntimeArtifacts(unittest.TestCase):
    def test_01_source_photos_exist_with_exact_case(self):
        _, rows = read_csv()
        present = [row for row in rows if row["availability"] != "missing"]
        self.assertEqual(len(present), 274)
        for row in present:
            self.assertTrue(case_consistent(row["source_path"]), row["source_path"])
        # run5：photos/_source_jpeg/ 是 130 个转码原件备份，必须排除在源文件集合外。
        disk = [path for path in (PROJECT_ROOT / "photos").rglob("*")
                if path.is_file() and path.relative_to(PROJECT_ROOT / "photos").parts[0]
                != "_source_jpeg"]
        self.assertEqual(len(disk), 274)
        backups = [path for path in (PROJECT_ROOT / "photos" / "_source_jpeg").rglob("*.jpg")]
        self.assertEqual(len(backups), 130)
        if INVENTORY_JSON.is_file():
            inventory = json.loads(INVENTORY_JSON.read_text(encoding="utf-8"))
            by_name = {item["file"]: item for item in inventory}
            for row in present:
                entry = by_name.get(Path(row["source_path"]).name)
                self.assertIsNotNone(entry, row["record_id"])
                self.assertEqual(row["sha256"], entry.get("sha256"), row["record_id"])

    def test_02_runtime_png_count_and_signature(self):
        _, rows = read_csv()
        rooms = sorted((ASSETS / "rooms").glob("*.png"))
        cards = sorted((ASSETS / "cards").rglob("*.png"))
        characters = sorted((ASSETS / "characters").glob("*.png"))
        placeholders = sorted((ASSETS / "placeholders").glob("*.png"))
        # run6：六类渲染面各自的运行时目录（274 位里占 132 位）
        monsters = sorted((ASSETS / "monsters").glob("*.png"))
        haunts = sorted((ASSETS / "haunts").glob("*.png"))
        endings = sorted((ASSETS / "endings").glob("*.png"))
        card_backs = sorted((ASSETS / "card_backs").glob("*.png"))
        room_backs = sorted((ASSETS / "room_backs").glob("*.png"))
        dice = sorted((ASSETS / "dice").glob("*.png"))
        # 50 rooms / 80 cards / 12 characters / 3 placeholders = 145（与原断言同源）
        self.assertEqual(len(rooms), 50)
        self.assertEqual(len(cards), 80)
        self.assertEqual(len(characters), 12)
        self.assertEqual(len(placeholders), 3)
        # run6 六类：52 monsters / 70 haunts / 2 endings / 3 card_backs / 2 room_backs / 3 dice
        self.assertEqual(len(monsters), 52)
        self.assertEqual(len(haunts), 70)
        self.assertEqual(len(endings), 2)
        self.assertEqual(len(card_backs), 3)
        self.assertEqual(len(room_backs), 2)
        self.assertEqual(len(dice), 3)
        # 145（五类含占位）+ 132（六类渲染面）= 277 张运行时 PNG
        total = (len(rooms) + len(cards) + len(characters) + len(placeholders)
                 + len(monsters) + len(haunts) + len(endings)
                 + len(card_backs) + len(room_backs) + len(dice))
        self.assertEqual(total, 277)
        runtime_paths = {row["runtime_path"] for row in rows}
        self.assertEqual(len(runtime_paths), 274)
        for rel in runtime_paths:
            path = PROJECT_ROOT / rel
            self.assertTrue(path.is_file(), rel)
            with path.open("rb") as handle:
                self.assertEqual(handle.read(8), PNG_SIGNATURE, rel)

    def test_03_runtime_sizes_match_runtime_specs(self):
        _, rows = read_csv()
        for row in rows:
            path = PROJECT_ROOT / row["runtime_path"]
            self.assertEqual(png_size(path), RUNTIME_SIZE[row["asset_type"]],
                             "%s %s" % (row["record_id"], row["runtime_path"]))

    def test_04_runtime_paths_are_inside_assets_and_case_exact(self):
        _, rows = read_csv()
        prefix = "source/desktop/game/assets/"
        for row in rows:
            self.assertTrue(row["runtime_path"].startswith(prefix), row["record_id"])
            self.assertNotIn("..", row["runtime_path"], row["record_id"])
            self.assertTrue(case_consistent(row["runtime_path"]), row["runtime_path"])


# ----------------------------------------------------------------------
# 3. 注册表契约
# ----------------------------------------------------------------------
class TestRegistryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()

    def test_01_resolve_all_target_refs_and_record_ids(self):
        self.assertEqual(len(self.registry), EXPECTED_TOTAL)
        for target_ref in self.registry.target_refs():
            self.assertIsNotNone(self.registry.resolve(target_ref), target_ref)
        for record_id in self.registry.record_ids():
            self.assertIsNotNone(self.registry.resolve(record_id), record_id)
        # run5 v2：0 missing（旧 47）
        self.assertEqual(len(self.registry.missing()), 0)

    def test_02_unknown_and_empty_keys_return_none(self):
        for key in (None, "", "   ", "no:such:key", 274, ["x"], "room:no_such_room"):
            self.assertIsNone(self.registry.resolve(key), repr(key))

    def test_03_case_insensitive_and_bare_id(self):
        row = first_row("card_omen")
        upper = row["target_ref"].upper()
        self.assertEqual(self.registry.resolve(upper).record_id, row["record_id"])
        # 裸 id 取运行时键末段（target_ref 是 content.py 引用，末段是"集合#id"）
        bare = row["runtime_key"].split(":")[-1]
        self.assertEqual(self.registry.resolve(bare).record_id, row["record_id"])

    def test_04_character_faces_are_distinct(self):
        front = self.registry.resolve("character:card_1:f0")
        back = self.registry.resolve("character:card_1:f1")
        self.assertIsNotNone(front)
        self.assertIsNotNone(back)
        self.assertNotEqual(front.record_id, back.record_id)
        self.assertIsNone(self.registry.resolve("content.py:CHARACTER_FACES#card_1"))

    def test_04b_target_ref_and_runtime_key_resolve_to_same_row(self):
        _, rows = read_csv()
        for row in rows:
            self.assertTrue(row["target_ref"].startswith("content.py:"), row["target_ref"])
            for key in ("target_ref", "runtime_key", "record_id", "content_ref"):
                ref = self.registry.resolve(row[key])
                self.assertIsNotNone(ref, "%s %s" % (row["record_id"], key))
                self.assertEqual(ref.record_id, row["record_id"], "%s %s" % (row["record_id"], key))
                self.assertEqual(ref.target_ref, row["target_ref"], row["record_id"])
                self.assertEqual(ref.runtime_key, row["runtime_key"], row["record_id"])

    def test_05_duplicate_record_id_rejected(self):
        with self.assertRaises(ValueError):
            AssetRegistry.load(FIXTURES / "duplicate_record_id.json",
                               base_dir=str(PROJECT_ROOT))

    def test_06_bom_json_is_readable(self):
        registry = AssetRegistry.load(FIXTURES / "bom.json", base_dir=str(PROJECT_ROOT))
        self.assertEqual(len(registry), 2)
        self.assertIsNotNone(registry.resolve("room:bom_room"))
        self.assertIsNotNone(registry.resolve("card:event:bom_event"))

    def test_07_path_traversal_keys_rejected(self):
        registry = AssetRegistry.load(FIXTURES / "path_traversal.json",
                                      base_dir=str(PROJECT_ROOT))
        for key in ("../escape", "room:../escape", "content.py:FIXTURES#../../etc/passwd",
                    "qa/fixtures/outside/evil.png"):
            self.assertIsNone(registry.resolve(key), key)
        self.assertIsNotNone(registry.resolve("room:traversal_control"))

    def test_08_validate_reports_outside_assets_root(self):
        registry = AssetRegistry.load(FIXTURES / "path_traversal.json",
                                      base_dir=str(PROJECT_ROOT))
        issues = registry.validate(ASSETS)
        codes = {issue["code"] for issue in issues}
        self.assertIn("runtime_outside_assets_root", codes)
        self.assertIn("runtime_file_absent", codes)

    def test_09_validate_real_table_is_clean(self):
        self.assertEqual(self.registry.validate(ASSETS), [])

    def test_10_missing_manifest_raises(self):
        missing = QA_DIR / "__no_such_manifest__.json"
        with self.assertRaises(FileNotFoundError) as ctx:
            AssetRegistry.load(missing)
        self.assertIn(str(missing), str(ctx.exception))

    def test_11_missing_records_without_sibling_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "asset_mapping.json"
            shutil.copy(str(FIXTURES / "mapping_without_records.json"), str(target))
            with self.assertRaises(ValueError):
                AssetRegistry.load(target)

    def test_12_mapping_falls_back_to_sibling_p_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            shutil.copy(str(FIXTURES / "mapping_without_records.json"),
                        str(directory / "asset_mapping.json"))
            shutil.copy(str(FIXTURES / "bom.json"), str(directory / "p_table.json"))
            registry = AssetRegistry.load(directory / "asset_mapping.json",
                                          base_dir=str(PROJECT_ROOT))
            self.assertEqual(len(registry), 2)

    def test_13_asset_ref_api_shape(self):
        key = first_row("room", exclude_availability="missing")["target_ref"]
        ref = self.registry.resolve(key)
        self.assertEqual(ref["record_id"], ref.record_id)
        self.assertEqual(ref.get("target_ref"), ref.target_ref)
        self.assertEqual(ref.get("__absent__", "fallback"), "fallback")
        self.assertEqual(set(ref.keys()), set(ref.to_dict()))
        self.assertTrue(ref.exists())
        self.assertTrue(bool(ref))
        self.assertFalse(ref.is_missing)
        self.assertFalse(ref.is_placeholder)
        self.assertIn("AssetRef", repr(ref))
        # run5 v2：真实表 274 位全部落实，已无 missing 行；用合成清单守住
        # "missing / placeholder 语义"这条契约（不删断言，只换样本来源）。
        payload = json.loads(PTABLE_JSON.read_text(encoding="utf-8"))
        record = copy.deepcopy(payload["records"][0])
        record.update({
            "record_id": "P-CHR-901",
            "target_ref": "content.py:FIXTURES#missing_probe",
            "runtime_key": "character:missing_probe:f0",
            "asset_type": "character",
            "availability": "missing",
            "mapping_status": "pending_missing",
            "runtime_status": "placeholder",
            "runtime_path": "source/desktop/game/assets/placeholders/character_missing.png",
            "source_path": "",
            "source_file": "",
            "bytes": None,
            "sha256": "",
            "missing_note": "合成样本：验证 missing/placeholder 语义",
        })
        payload["records"].append(record)
        directory = tempfile.mkdtemp(prefix="ptable_assetref_")
        self.addCleanup(shutil.rmtree, directory, True)
        manifest = Path(directory) / "p_table.json"
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        synthetic = AssetRegistry.load(manifest, base_dir=str(PROJECT_ROOT))
        missing = synthetic.resolve("character:missing_probe:f0")
        self.assertTrue(missing.is_missing)
        self.assertTrue(missing.is_placeholder)


# ----------------------------------------------------------------------
# 4. 负样本与异常路径
# ----------------------------------------------------------------------
class TestNegativeSamples(unittest.TestCase):
    def test_01_zero_byte_png_not_decodable(self):
        self.assertIsNone(png_size(FIXTURES / "zero_byte.png"))

    def test_02_corrupt_png_not_decodable(self):
        path = FIXTURES / "corrupt.png"
        self.assertTrue(path.read_bytes().startswith(PNG_SIGNATURE))
        self.assertIsNone(png_size(path))

    def test_02b_png_size_missing_file_returns_none(self):
        self.assertIsNone(png_size(FIXTURES / "__absent__.png"))

    def test_03_bad_json_raises_value_error(self):
        with self.assertRaises(ValueError):
            AssetRegistry.load(FIXTURES / "bad.json")

    def _temp_manifest(self, mutate):
        payload = json.loads(PTABLE_JSON.read_text(encoding="utf-8"))
        record = copy.deepcopy(payload["records"][0])
        mutate(record, payload)
        payload["records"] = [record]
        directory = tempfile.mkdtemp(prefix="ptable_negative_")
        self.addCleanup(shutil.rmtree, directory, True)
        path = Path(directory) / "p_table.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return AssetRegistry.load(path, base_dir=str(PROJECT_ROOT))

    def test_04_runtime_file_absent_is_reported(self):
        def mutate(record, payload):
            record["record_id"] = "P-ROOM-901"
            record["target_ref"] = "content.py:FIXTURES#absent_probe"
            record["runtime_key"] = "room:absent_probe"
            record["availability"] = "partial"
            record["runtime_status"] = "ok"
            record["runtime_path"] = "source/desktop/game/assets/rooms/__absent__.png"
            record["asset_type"] = "room"

        registry = self._temp_manifest(mutate)
        self.assertIsNotNone(registry.resolve("room:absent_probe"))
        codes = {issue["code"] for issue in registry.validate(ASSETS)}
        self.assertIn("runtime_file_absent", codes)

    def test_05_corrupt_runtime_file_is_reported_not_png(self):
        def mutate(record, payload):
            record["record_id"] = "P-ROOM-902"
            record["target_ref"] = "content.py:FIXTURES#corrupt_probe"
            record["runtime_key"] = "room:corrupt_probe"
            record["availability"] = "partial"
            record["runtime_status"] = "ok"
            record["runtime_path"] = "source/desktop/game/qa/fixtures/corrupt.png"
            record["asset_type"] = "room"

        registry = self._temp_manifest(mutate)
        codes = {issue["code"] for issue in registry.validate(ASSETS)}
        self.assertIn("runtime_not_png", codes)


# ----------------------------------------------------------------------
# 5. 管线辅助函数（matcher / 规范化 / 发布字段）
# ----------------------------------------------------------------------
class TestPipelineHelpers(unittest.TestCase):
    def test_01_sniff_format_by_magic(self):
        directory = tempfile.mkdtemp(prefix="ptable_magic_")
        self.addCleanup(shutil.rmtree, directory, True)
        cases = {
            "a.png": (PNG_SIGNATURE + b"\x00\x00", "png"),
            "b.png": (b"\xff\xd8\xff\xe0rest", "jpeg"),
            "c.bin": (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp"),
            "d.bin": (b"not-an-image", "unknown"),
        }
        for name, (payload, expected) in cases.items():
            path = Path(directory) / name
            path.write_bytes(payload)
            self.assertEqual(asset_pipeline.sniff_format(path), expected, name)

    def test_02_dimensions_and_ratio_helpers(self):
        self.assertEqual(asset_pipeline.dimensions_text(0, 5), "")
        self.assertEqual(asset_pipeline.dimensions_text(2048, 2048), "2048x2048")
        self.assertEqual(asset_pipeline.aspect_ratio_text(0, 0), "")
        self.assertEqual(asset_pipeline.aspect_ratio_text(1773, 2364), "3:4")
        self.assertEqual(asset_pipeline.aspect_ratio_text(2048, 2048), "1:1")

    def test_03_rel_path_falls_back_outside_project_root(self):
        outside = Path(tempfile.gettempdir()) / "ptable_outside_probe.png"
        rel = asset_pipeline._rel(outside)
        self.assertTrue(rel.endswith("/ptable_outside_probe.png"), rel)
        self.assertFalse(rel.startswith("source/"), rel)

    def test_04_probe_photo_isolates_corrupt_file(self):
        facts = asset_pipeline.probe_photo(FIXTURES / "corrupt.png")
        self.assertEqual(facts["decodable"], "failed")
        self.assertEqual(facts["format"], "png")
        self.assertTrue(facts["error"])
        real = asset_pipeline.probe_photo(PROJECT_ROOT / first_row(
            "room", exclude_availability="missing")["source_path"])
        self.assertEqual(real["decodable"], "ok")
        # run5 v2：130 张 JPEG 已无损转码为真 PNG，真实房间源图现在是 png
        self.assertEqual(real["format"], "png")

    def test_05_match_photo_degrades_in_order(self):
        index = {
            "room": {
                "exact": {
                    "entrance_hall": [{"stem": "entrance_hall"}],
                    "ambiguous_room": [{"stem": "a"}, {"stem": "b"}],
                },
                "norm": {"entrance_hall": [{"stem": "entrance-hall"}]},
            }
        }
        facts, how = asset_pipeline.match_photo(
            {"family": "room", "match_stem": "entrance_hall"}, index)
        self.assertEqual(how, "exact_id")
        facts, how = asset_pipeline.match_photo(
            {"family": "room", "match_stem": "entrance-hall"}, index)
        self.assertEqual(how, "normalized_id")
        facts, how = asset_pipeline.match_photo(
            {"family": "room", "match_stem": "ambiguous_room"}, index)
        self.assertEqual(how, "ambiguous")
        facts, how = asset_pipeline.match_photo(
            {"family": "room", "match_stem": "nope"}, index)
        self.assertIsNone(facts)
        self.assertEqual(how, "unmatched")
        facts, how = asset_pipeline.match_photo(
            {"family": "character", "match_stem": "card_1_0"}, index)
        self.assertEqual(how, "no_dir")
        self.assertIsNone(facts)

        # run5：47 位落实后真实表已 0 missing，但 make_missing_record 仍是"缺图兜底"
        # 的生产路径（照片被删/新内容位未出图时会走到）。这里直接驱动它，保证这条
        # 路径不被覆盖率挖空。
        def slot(family, effect_id="", collection="EVENT_SUPPLEMENTAL_SPECS"):
            return {
                "family": family,
                "collection": collection,
                "slot_id": "event_probe",
                "match_stem": "event_probe",
                "target_ref": "content.py:%s#event_probe" % collection,
                "runtime_key": "card:event:event_probe",
                "content_ref": "content.py:%s#event_probe" % collection,
                "semantic_hint": "事件卡：探针",
                "match_candidate": "event_probe",
                "name": "探针",
                "source_name": "Probe",
                "effect_id": effect_id,
                "runtime_name": "event_probe",
            }

        fallback_row = asset_pipeline.make_missing_record(
            slot("event", effect_id="event_lights_out"), {"event_lights_out"})
        self.assertEqual(fallback_row["availability"], "missing")
        self.assertEqual(fallback_row["mapping_status"], "fallback")
        self.assertEqual(fallback_row["runtime_status"], "fallback")
        self.assertTrue(fallback_row["missing_note"])
        self.assertEqual(fallback_row["bytes"], None)
        self.assertEqual(fallback_row["sha256"], "")

        placeholder_row = asset_pipeline.make_missing_record(slot("event"), set())
        self.assertEqual(placeholder_row["mapping_status"], "pending_missing")
        self.assertEqual(placeholder_row["runtime_status"], "placeholder")
        self.assertIn("placeholders/", placeholder_row["runtime_path"])

        character_slot = slot("character", collection="CHARACTER_FACES")
        character_slot.update(runtime_key="character:card_1:f0", slot_id="card_1_0")
        character_row = asset_pipeline.make_missing_record(character_slot, set())
        self.assertIn("character_missing.png", character_row["runtime_path"])
        self.assertTrue(character_row["alpha_required"])

        room_slot = slot("room", collection="ROOM_SUPPLEMENTAL_SPECS")
        room_slot.update(runtime_key="room:storeroom", slot_id="storeroom")
        room_row = asset_pipeline.make_missing_record(room_slot, set())
        self.assertIn("room_missing.png", room_row["runtime_path"])

        # _partial_note / transcode_index（run5 新增溯源入口）
        facts = {"dir": "room", "ext": "png", "format": "jpeg"}
        note = asset_pipeline._partial_note(facts, (512, 512))
        self.assertIn("ext_mismatch", note)
        self.assertIn("512x512", note)
        index = asset_pipeline.transcode_index()
        self.assertEqual(len(index), 130)
        sample = next(iter(index))
        self.assertIn("src_sha256", index[sample])
        self.assertIn("backup", index[sample])

        # 规范化主干的二级降级：norm 桶里出现多个候选 → ambiguous
        index2 = {
            "room": {
                "exact": {},
                "norm": {"dup_room": [{"stem": "a"}, {"stem": "b"}]},
            }
        }
        facts2, how2 = asset_pipeline.match_photo(
            {"family": "room", "match_stem": "dup_room"}, index2)
        self.assertEqual(how2, "ambiguous")
        self.assertEqual(facts2["stem"], "a")
        # 规范化主干折叠连续下划线
        self.assertEqual(asset_pipeline._norm_stem("a--b"), "a_b")
        # 转码清单损坏时必须降级为空表而不是抛异常
        broken = Path(tempfile.mkdtemp(prefix="ptable_manifest_")) / "broken.json"
        self.addCleanup(shutil.rmtree, str(broken.parent), True)
        broken.write_text("{not json", encoding="utf-8")
        original_manifest = asset_pipeline.TRANSCODE_MANIFEST
        try:
            asset_pipeline.TRANSCODE_MANIFEST = broken
            asset_pipeline._TRANSCODE_INDEX = None
            self.assertEqual(asset_pipeline.transcode_index(), {})
        finally:
            asset_pipeline.TRANSCODE_MANIFEST = original_manifest
            asset_pipeline._TRANSCODE_INDEX = None

    def test_06_normalize_room_and_card_produce_spec_png(self):
        directory = tempfile.mkdtemp(prefix="ptable_normalize_")
        self.addCleanup(shutil.rmtree, directory, True)
        room_row = first_row("room", exclude_availability="missing")
        size = asset_pipeline.normalize_room(
            PROJECT_ROOT / room_row["source_path"], Path(directory) / "room.png")
        self.assertEqual(size, (512, 512))
        self.assertEqual(png_size(Path(directory) / "room.png"), (512, 512))

        card_row = first_row("card_event", exclude_availability="missing")
        size = asset_pipeline.normalize_card(
            PROJECT_ROOT / card_row["source_path"], Path(directory) / "card.png")
        self.assertEqual(size, (480, 672))
        self.assertEqual(png_size(Path(directory) / "card.png"), (480, 672))

    def test_07_normalize_assets_refuses_to_write_photos(self):
        room_row = first_row("room", exclude_availability="missing")
        forbidden = asset_pipeline.PHOTOS_DIR / "__must_not_write__.png"
        record = {
            "record_id": "P-ROOM-950",
            "target_ref": "room:forbidden_probe",
            "runtime_path": "photos/__must_not_write__.png",
            "source_path": room_row["source_path"],
            "availability": "partial",
            "_runtime_abs": forbidden,
            "_family": "room",
        }
        result = asset_pipeline.normalize_assets([record])
        self.assertEqual(result["written"], 0)
        self.assertEqual(len(result["failures"]), 1)
        self.assertIn("拒绝写入 photos", result["failures"][0]["reason"])
        self.assertFalse(forbidden.exists(), "photos/ 不得被写入")

    def test_08_assign_canonical_ids_marks_duplicate(self):
        records = [
            {"record_id": "P-ROOM-001", "availability": "partial", "sha256": "a" * 64},
            {"record_id": "P-ROOM-002", "availability": "duplicate", "sha256": "a" * 64},
            {"record_id": "P-ROOM-003", "availability": "missing", "sha256": ""},
        ]
        asset_pipeline.assign_canonical_ids(records)
        self.assertEqual(records[0]["canonical_record_id"], "P-ROOM-001")
        self.assertEqual(records[1]["canonical_record_id"], "P-ROOM-001")
        self.assertEqual(records[2]["canonical_record_id"], "P-ROOM-003")

    def test_09_verified_at_derives_from_source_date_epoch(self):
        with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "1700000000"}):
            self.assertEqual(asset_pipeline.verification_date(), "2023-11-14")
            self.assertEqual(asset_pipeline.generation_date(), "2023-11-14")
        with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "not-a-number"}):
            self.assertEqual(asset_pipeline.verification_date(),
                             asset_pipeline.VERIFIED_AT_FALLBACK)
        # 超出 datetime 可表示范围的 epoch：必须退回固定日期，不得抛异常
        with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "9" * 20}):
            self.assertEqual(asset_pipeline.verification_date(),
                             asset_pipeline.VERIFIED_AT_FALLBACK)
            self.assertEqual(asset_pipeline.generation_date(),
                             datetime.now().strftime("%Y-%m-%d"))

    def test_10_runtime_rel_path_rejects_character(self):
        # run5 v2：角色 12 位已接通 photos/role/ 真图，runtime 落到 assets/characters/；
        # "拒绝未知类别"这条断言保留，样本从 character 换成真正未知的 family。
        path = asset_pipeline.runtime_rel_path(
            {"family": "character", "runtime_name": "card_1_0"})
        self.assertEqual(path.parent.name, "characters")
        self.assertEqual(path.name, "card_1_0.png")
        with self.assertRaises(ValueError):
            asset_pipeline.runtime_rel_path({"family": "no_such_family",
                                             "runtime_name": "probe"})


# ----------------------------------------------------------------------
# 6. 注册表语义冲突分支
# ----------------------------------------------------------------------
class TestRegistryValidationConflicts(unittest.TestCase):
    def _record(self, record_id, target_ref, runtime_path, **extra):
        row = {
            "record_id": record_id,
            "target_ref": target_ref,
            "asset_type": "room",
            "runtime_path": runtime_path,
            "availability": "missing",
            "mapping_status": "pending_missing",
            "missing_note": "",
            "source_path": "",
            "runtime_status": "placeholder",
            "fallback_ref": "",
            "sha256": "",
        }
        row.update(extra)
        return row

    def test_01_semantic_conflicts_are_reported(self):
        placeholder = "source/desktop/game/assets/placeholders/room_missing.png"
        real_room = first_row("room", exclude_availability="missing")["runtime_path"]
        real_event = first_row("card_event", exclude_availability="missing")["runtime_path"]
        records = [
            # 有回退引用但目标不存在、格式不是 record_id、pending_missing 不应带回退
            self._record("P-ROOM-801", "room:conflict_a", placeholder,
                         fallback_ref="card:event:nope"),
            # mapping_status=fallback 却没有 fallback_ref；placeholder 指向非 placeholders 目录
            self._record("P-ROOM-802", "room:conflict_b", real_room,
                         mapping_status="fallback", missing_note="x"),
            # runtime_status=fallback 却没有 fallback_ref
            self._record("P-ROOM-803", "room:conflict_c", real_event,
                         runtime_status="fallback", missing_note="x"),
            # missing 行不应带 source_path
            self._record("P-ROOM-804", "room:conflict_d", placeholder,
                         source_path="photos/room/__fake__.png", missing_note="x"),
        ]
        payload = {
            "base_dir": PROJECT_ROOT.name,
            "runtime_specs": {"room": {"width": 512, "height": 512, "format": "png"},
                              "card": {"width": 480, "height": 672, "format": "png"}},
            "records": records,
        }
        directory = tempfile.mkdtemp(prefix="ptable_validate_")
        self.addCleanup(shutil.rmtree, directory, True)
        manifest = Path(directory) / "p_table.json"
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        registry = AssetRegistry.load(manifest, base_dir=str(PROJECT_ROOT))
        codes = {issue["code"] for issue in registry.validate(ASSETS)}
        for expected in ("missing_note_absent", "missing_has_source",
                         "pending_missing_with_fallback", "fallback_unresolved",
                         "fallback_not_record_id", "fallback_mapping_without_ref",
                         "placeholder_path_suspect", "fallback_without_ref"):
            self.assertIn(expected, codes)


# ----------------------------------------------------------------------
# 7. 回归：重复加载 / 重复构建
# ----------------------------------------------------------------------
class TestRepeatability(unittest.TestCase):
    def test_01_two_registry_loads_identical(self):
        first = load_registry()
        second = load_registry()
        self.assertEqual(len(first), len(second))
        self.assertEqual(first.summary(), second.summary())
        self.assertEqual(first.record_ids(), second.record_ids())
        self.assertEqual(first.target_refs(), second.target_refs())
        for key in first.target_refs():
            a, b = first.resolve(key), second.resolve(key)
            self.assertEqual(a.to_dict(), b.to_dict())

    def test_02_two_generations_identical(self):
        # 预热一次：首次生成（或管线描述变更后的首次）会改写 assets/ 三件产物，
        # setUpModule 已先冻结当前产物作为对照；这里再跑一次必须逐字节一致，
        # 不跳过、不放宽断言（历史上 142 门槛返回 1，曾把本条误报为"生成不稳定"）。
        self.assertIn("csv", _GENERATION_SNAPSHOT, "setUpModule 未冻结构建快照")
        run_ptable_stage()
        self.assertEqual(PTABLE_CSV.read_bytes(), _GENERATION_SNAPSHOT["csv"],
                         "两次构建的 CSV 应逐字节一致")
        current = read_json()
        previous = copy.deepcopy(_GENERATION_SNAPSHOT["json"])
        self.assertEqual(current["records"], previous["records"])
        self.assertEqual(current["stats"], previous["stats"])
        self.assertEqual(current["content"], previous["content"])
        self.assertEqual(current["schema"], previous["schema"])
        current.pop("generated_at", None)
        previous.pop("generated_at", None)
        self.assertEqual(current, previous)


# ----------------------------------------------------------------------
# 6. UI 绑定（Tk）
# ----------------------------------------------------------------------
class TestUiBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reason = ""
        cls.root = None
        try:
            import tkinter
        except Exception as exc:  # 明确 FAIL，不 skip
            cls.reason = "import tkinter 失败：%s: %s" % (type(exc).__name__, exc)
            return
        try:
            cls.root = tkinter.Tk()
            cls.root.withdraw()
        except Exception as exc:
            cls.reason = "Tk() 初始化失败（无可用显示）：%s: %s" % (type(exc).__name__, exc)

    @classmethod
    def tearDownClass(cls):
        if cls.root is not None:
            try:
                cls.root.destroy()
            except Exception:
                pass
        ui_asset_binding.reset_default_caches()

    def setUp(self):
        if self.reason:
            self.fail("UI 用例 not-run：%s（不计 PASS）" % self.reason)
        self.registry = load_registry()

    def test_01_load_room_and_card_photos(self):
        room = first_row("room", exclude_availability="missing")
        card = first_row("card_event", exclude_availability="missing")
        cache = ui_asset_binding.AssetImageCache(capacity=8)

        room_photo = ui_asset_binding.load_asset_photo(
            self.registry, room["target_ref"], self.root, (256, 256), cache)
        self.assertIsNotNone(room_photo, room["target_ref"])
        self.assertLessEqual(room_photo.width(), 256)
        self.assertLessEqual(room_photo.height(), 256)

        card_photo = ui_asset_binding.load_asset_photo(
            self.registry, card["target_ref"], self.root, (256, 256), cache)
        self.assertIsNotNone(card_photo, card["target_ref"])
        self.assertLessEqual(card_photo.width(), 256)
        self.assertLessEqual(card_photo.height(), 256)
        ratio = card_photo.height() / float(card_photo.width())
        self.assertAlmostEqual(ratio, 672 / 480.0, delta=0.02)

        again = ui_asset_binding.load_asset_photo(
            self.registry, room["target_ref"], self.root, (256, 256), cache)
        self.assertIs(again, room_photo, "重复绑定应命中缓存返回同一对象")
        stats = cache.stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 2)
        self.assertEqual(stats["size"], 2)

    def test_02_missing_character_uses_placeholder(self):
        # run5 v2：真实表已 0 missing，角色 12 位都是真图。用合成 missing 行
        # 继续守住"缺图回落占位图"这条契约（样本来源换了，断言一条没少）。
        payload = json.loads(PTABLE_JSON.read_text(encoding="utf-8"))
        record = copy.deepcopy(first_json_row(payload, "character"))
        record.update({
            "record_id": "P-CHR-902",
            "target_ref": "content.py:FIXTURES#ui_missing_probe",
            "runtime_key": "character:ui_missing_probe:f0",
            "asset_type": "character",
            "availability": "missing",
            "mapping_status": "pending_missing",
            "runtime_status": "placeholder",
            "runtime_path": "source/desktop/game/assets/placeholders/character_missing.png",
            "source_path": "",
            "source_file": "",
            "bytes": None,
            "sha256": "",
            "missing_note": "合成样本：验证占位图回落",
        })
        payload["records"].append(record)
        directory = tempfile.mkdtemp(prefix="ptable_ui_missing_")
        self.addCleanup(shutil.rmtree, directory, True)
        manifest = Path(directory) / "p_table.json"
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        registry = AssetRegistry.load(manifest, base_dir=str(PROJECT_ROOT))

        cache = ui_asset_binding.AssetImageCache(capacity=4)
        photo = ui_asset_binding.load_asset_photo(
            registry, "character:ui_missing_probe:f0", self.root, (256, 256), cache)
        self.assertIsNotNone(photo, "缺图应回落到占位图而不是 None")
        self.assertLessEqual(photo.width(), 256)
        self.assertLessEqual(photo.height(), 256)
        self.assertEqual(cache.stats()["misses"], 1)

    def test_03_unknown_key_returns_none(self):
        cache = ui_asset_binding.AssetImageCache(capacity=4)
        self.assertIsNone(ui_asset_binding.load_asset_photo(
            self.registry, "no:such:key", self.root, (256, 256), cache))
        self.assertIsNone(ui_asset_binding.load_asset_photo(
            self.registry, "../escape", self.root, (256, 256), cache))
        self.assertEqual(cache.stats()["misses"], 2)

    def test_04_lru_eviction_is_bounded(self):
        cache = ui_asset_binding.AssetImageCache(capacity=2)
        keys = [
            first_row("room", exclude_availability="missing")["target_ref"],
            first_row("card_event", exclude_availability="missing")["target_ref"],
            first_row("character")["target_ref"],
        ]
        for key in keys:
            self.assertIsNotNone(ui_asset_binding.load_asset_photo(
                self.registry, key, self.root, (128, 128), cache), key)
        stats = cache.stats()
        self.assertEqual(stats["size"], 2)
        self.assertEqual(stats["evictions"], 1)
        self.assertEqual(stats["misses"], 3)

    def test_05_corrupt_runtime_file_falls_back_to_placeholder(self):
        payload = json.loads(PTABLE_JSON.read_text(encoding="utf-8"))
        record = copy.deepcopy(payload["records"][0])
        record.update({
            "record_id": "P-ROOM-903",
            "target_ref": "content.py:FIXTURES#ui_corrupt_probe",
            "runtime_key": "room:ui_corrupt_probe",
            "asset_type": "room",
            "availability": "partial",
            "runtime_status": "ok",
            "runtime_path": "source/desktop/game/qa/fixtures/corrupt.png",
        })
        payload["records"].append(record)
        directory = tempfile.mkdtemp(prefix="ptable_ui_")
        self.addCleanup(shutil.rmtree, directory, True)
        manifest = Path(directory) / "p_table.json"
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        registry = AssetRegistry.load(manifest, base_dir=str(PROJECT_ROOT))
        cache = ui_asset_binding.AssetImageCache(capacity=4)
        photo = ui_asset_binding.load_asset_photo(
            registry, "room:ui_corrupt_probe", self.root, (128, 128), cache)
        self.assertIsNotNone(photo, "坏图应回落到占位图")
        self.assertGreaterEqual(cache.stats()["errors"], 1)


class TestProbeCache(unittest.TestCase):
    """run5 性能修复：来源探测缓存的失效键与幂等落盘。

    覆盖点：缓存命中/失效、版本不匹配、损坏 JSON、mtime 变化、
    幂等写（内容不变不落盘）、读失败与写失败都被吞掉不影响构建。
    """

    def setUp(self):
        import asset_pipeline

        self.ap = asset_pipeline
        self.directory = Path(tempfile.mkdtemp(prefix="probe_cache_"))
        self.addCleanup(shutil.rmtree, str(self.directory), True)
        self.cache_path = self.directory / ".probe_cache.json"
        self.original_cache_path = asset_pipeline.PROBE_CACHE_PATH
        asset_pipeline.PROBE_CACHE_PATH = self.cache_path
        self.addCleanup(setattr, asset_pipeline, "PROBE_CACHE_PATH",
                        self.original_cache_path)
        self.png = self.directory / "probe.png"
        self._make_png(self.png, (8, 8))

    @staticmethod
    def _make_png(path, size):
        from PIL import Image
        Image.new("RGB", size, (10, 20, 30)).save(str(path), format="PNG")

    def test_01_miss_then_hit(self):
        cache = {}
        facts1, hit1 = self.ap.probe_photo_cached(self.png, cache)
        self.assertFalse(hit1, "首次应为未命中")
        self.assertEqual(facts1["decodable"], "ok")
        self.assertEqual((facts1["width"], facts1["height"]), (8, 8))
        facts2, hit2 = self.ap.probe_photo_cached(self.png, cache)
        self.assertTrue(hit2, "同 bytes/mtime 应命中缓存")
        self.assertEqual(facts2["sha256"], facts1["sha256"])
        self.assertEqual(facts2["width"], facts1["width"])

    def test_02_mtime_change_invalidates(self):
        cache = {}
        self.ap.probe_photo_cached(self.png, cache)
        _, hit_before = self.ap.probe_photo_cached(self.png, cache)
        self.assertTrue(hit_before)
        os.utime(str(self.png), (1, 1))
        _, hit_after = self.ap.probe_photo_cached(self.png, cache)
        self.assertFalse(hit_after, "mtime 变化必须失效")

    def test_03_invalid_version_ignored(self):
        self.cache_path.write_text(
            json.dumps({"version": 999, "entries": {"x": {}}}), encoding="utf-8")
        self.assertEqual(self.ap._load_probe_cache(), {})

    def test_04_corrupt_json_ignored(self):
        self.cache_path.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.ap._load_probe_cache(), {})

    def test_05_save_is_idempotent(self):
        entries = {"a": {"rel": "a", "bytes": 1, "mtime_ns": 2, "facts": {}}}
        self.ap._save_probe_cache(entries)
        self.assertTrue(self.cache_path.is_file(), "首次应落盘")
        stamp = self.cache_path.stat().st_mtime_ns
        self.ap._save_probe_cache(dict(entries))
        self.assertEqual(self.cache_path.stat().st_mtime_ns, stamp,
                         "内容不变不得重写（SAFE-01 只读审计）")
        entries["b"] = {"rel": "b", "bytes": 3, "mtime_ns": 4, "facts": {}}
        self.ap._save_probe_cache(entries)
        self.assertNotEqual(self.cache_path.stat().st_mtime_ns, stamp,
                            "内容变化必须落盘")

    def test_06_save_swallows_read_and_write_failure(self):
        # 目标是目录：read_text/write_text 都会抛，必须被吞掉
        blocker = self.directory / "as_dir.json"
        blocker.mkdir()
        self.ap.PROBE_CACHE_PATH = blocker
        try:
            self.ap._save_probe_cache({"a": {"rel": "a", "bytes": 1,
                                             "mtime_ns": 2, "facts": {}}})
        finally:
            self.ap.PROBE_CACHE_PATH = self.cache_path

    def test_07_missing_file_falls_back_without_hit(self):
        gone = self.directory / "not_here.png"
        facts, hit = self.ap.probe_photo_cached(gone, {})
        self.assertFalse(hit)
        self.assertEqual(facts["decodable"], "failed")

    def test_08_scan_photos_requires_dir(self):
        original = self.ap.PHOTOS_DIR
        self.ap.PHOTOS_DIR = self.directory / "no_such_photos"
        try:
            with self.assertRaises(SystemExit):
                self.ap.scan_photos()
        finally:
            self.ap.PHOTOS_DIR = original

    def test_09_scan_photos_reports_cache_hits(self):
        original = self.ap.PHOTOS_DIR
        photos_dir = self.directory / "photos"
        (photos_dir / "room").mkdir(parents=True)
        self._make_png(photos_dir / "room" / "r.png", (4, 4))
        self.ap.PHOTOS_DIR = photos_dir
        try:
            first = self.ap.scan_photos()
            second = self.ap.scan_photos()
        finally:
            self.ap.PHOTOS_DIR = original
        self.assertEqual(first["total"], 1)
        self.assertEqual(first.get("probe_cache_hits"), 0)
        self.assertEqual(second.get("probe_cache_hits"), 1,
                         "第二次扫描应命中缓存")

    def test_10_zero_dimension_marked_failed(self):
        broken = self.directory / "zero.png"
        from PIL import Image
        image = Image.new("RGB", (4, 4), (1, 2, 3))
        image.save(str(broken), format="PNG")
        original_open = Image.open

        class _Zero:
            size = (0, 0)
            mode = "RGB"
            info = {}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def verify(self):
                return None

            def getbands(self):
                return ("R", "G", "B")

        def fake_open(*args, **kwargs):
            return _Zero()

        Image.open = fake_open
        try:
            facts = self.ap.probe_photo(broken)
        finally:
            Image.open = original_open
        self.assertEqual(facts["decodable"], "failed")
        self.assertIn("zero dimension", facts["error"])


class TestManifestResolver(unittest.TestCase):
    """打包相关的清单查找与项目根探测（源码布局 + 冻结包布局）。"""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="manifest_resolve_"))
        self.addCleanup(shutil.rmtree, str(self.directory), True)

    def _make_frozen_tree(self, with_photos: bool):
        root = self.directory / "root"
        assets = root / "source" / "desktop" / "game" / "assets"
        assets.mkdir(parents=True)
        (assets / "p_table.json").write_text("{}", encoding="utf-8")
        if with_photos:
            (root / "photos").mkdir()
        return root, assets / "p_table.json"

    def test_01_candidates_first_is_source_layout(self):
        candidates = asset_registry.default_manifest_candidates()
        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(candidates[0].name, "asset_mapping.json")
        self.assertEqual(candidates[0].parent.name, "assets")
        # 其余候选必须指向 source/desktop/game/assets 布局
        self.assertTrue(any(
            str(path).replace("\\", "/").endswith(
                "source/desktop/game/assets/asset_mapping.json")
            for path in candidates[1:]))

    def test_02_resolve_manifest_path_hits_real_file(self):
        resolved = asset_registry.resolve_manifest_path()
        self.assertTrue(resolved.is_file(), resolved)
        self.assertEqual(resolved.name, "asset_mapping.json")

    def test_03_detect_root_frozen_layout_without_photos(self):
        root, manifest = self._make_frozen_tree(with_photos=False)
        detected = asset_registry.AssetRegistry._detect_project_root(
            manifest, "", None)
        self.assertEqual(detected, root.resolve())

    def test_04_detect_root_prefers_photos_layout(self):
        root, manifest = self._make_frozen_tree(with_photos=True)
        detected = asset_registry.AssetRegistry._detect_project_root(
            manifest, "", None)
        self.assertEqual(detected, root.resolve())

    def test_05_detect_root_honours_explicit_base_dir(self):
        root, manifest = self._make_frozen_tree(with_photos=False)
        explicit = self.directory / "explicit"
        explicit.mkdir()
        detected = asset_registry.AssetRegistry._detect_project_root(
            manifest, "", str(explicit))
        self.assertEqual(detected, explicit.resolve())


# ----------------------------------------------------------------------
# 11. run6 六类渲染面：规范化 / 槽位 / 运行时路径（asset_pipeline 侧）
# ----------------------------------------------------------------------
EXTRA_RUNTIME_SPECS = {
    "monster": ((512, 512), "monsters"),
    "haunt": ((1280, 720), "haunts"),
    "ending": ((1024, 576), "endings"),
    "card_back": ((480, 640), "card_backs"),
    "room_back": ((512, 512), "room_backs"),
    "dice": ((256, 256), "dice"),
}


class TestRenderSurfacePipeline(unittest.TestCase):
    """normalize_extra / collect_slots / runtime_rel_path / normalize_assets 分派。

    只用临时目录造小图：不写 photos/，也不写 assets/。
    """

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="ptable_extra_"))
        self.addCleanup(shutil.rmtree, str(self.directory), True)

    @staticmethod
    def _make_image(path, size, color=(10, 20, 30), mode="RGB"):
        from PIL import Image

        image = Image.new(mode, size, color)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        image.save(str(path), format="PNG")
        return image

    def test_01_normalize_extra_alpha_keeps_transparent_canvas(self):
        from PIL import Image

        source = self.directory / "src_alpha.png"
        self._make_image(source, (1000, 500), (200, 10, 10))
        target = self.directory / "out" / "alpha.png"

        size = asset_pipeline.normalize_extra(source, target, (512, 512), True)
        self.assertEqual(size, (512, 512))
        with Image.open(target) as out:
            self.assertEqual(out.size, (512, 512))
            self.assertEqual(out.mode, "RGBA")
            # 补边是透明画布（不是白底），否则怪物标记叠在地块上会出现白方块
            self.assertEqual(out.getpixel((0, 0))[3], 0)
            self.assertEqual(out.getpixel((511, 511))[3], 0)
            # 画面本身不透明：1000x500 -> 512x256，居中粘贴
            self.assertEqual(out.getpixel((256, 256))[3], 255)
            self.assertEqual(out.getpixel((256, 256))[:3], (200, 10, 10))

    def test_02_normalize_extra_opaque_pads_with_corner_mean(self):
        from PIL import Image

        source = self.directory / "src_rgb.png"
        self._make_image(source, (100, 50), (10, 20, 30))
        target = self.directory / "out" / "rgb.png"

        size = asset_pipeline.normalize_extra(source, target, (480, 640), False)
        self.assertEqual(size, (480, 640))
        with Image.open(target) as out:
            self.assertEqual(out.size, (480, 640))
            self.assertEqual(out.mode, "RGB")
            # 四角均值补边：源图纯色 -> 补边色等于源色
            self.assertEqual(out.getpixel((0, 0)), (10, 20, 30))
            self.assertEqual(out.getpixel((240, 320)), (10, 20, 30))

    def test_03_normalize_extra_never_exceeds_target(self):
        from PIL import Image

        source = self.directory / "wide.png"
        self._make_image(source, (2000, 500), (0, 128, 0))
        target = self.directory / "out" / "wide.png"

        asset_pipeline.normalize_extra(source, target, (256, 256), True)
        with Image.open(target) as out:
            self.assertEqual(out.size, (256, 256))
            bbox = out.getchannel("A").getbbox()
        self.assertIsNotNone(bbox)
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        self.assertLessEqual(width, 256)
        self.assertLessEqual(height, 256)
        self.assertEqual((width, height), (256, 64), "等比缩放：2000x500 -> 256x64")

    def test_04_normalize_card_and_character_sizes(self):
        from PIL import Image

        source = self.directory / "card.png"
        self._make_image(source, (1773, 2364), (5, 6, 7))
        card = self.directory / "out" / "card.png"
        self.assertEqual(asset_pipeline.normalize_card(source, card),
                         asset_pipeline.CARD_SIZE)
        with Image.open(card) as out:
            self.assertEqual(out.size, asset_pipeline.CARD_SIZE)
            self.assertEqual(out.mode, "RGB")
        portrait = self.directory / "out" / "char.png"
        self.assertEqual(asset_pipeline.normalize_character(source, portrait),
                         asset_pipeline.CHARACTER_SIZE)
        with Image.open(portrait) as out:
            self.assertEqual(out.size, asset_pipeline.CHARACTER_SIZE)
            self.assertEqual(out.mode, "RGBA")
            self.assertEqual(out.getpixel((0, 0))[3], 0)

    def test_05_collect_slots_has_eleven_categories(self):
        slots = asset_pipeline.collect_slots(asset_pipeline.load_content())
        self.assertEqual(len(slots), EXPECTED_TOTAL)
        counts = {}
        for slot in slots:
            counts[slot["family"]] = counts.get(slot["family"], 0) + 1
        self.assertEqual(counts, {
            "character": 12, "room": 50, "omen": 13, "item": 22, "event": 45,
            # 六类渲染面：monster 52 + haunt 70 + ending 2 + card_back 3
            # + room_back 2 + dice 3 = 132
            "monster": 52, "haunt": 70, "ending": 2,
            "card_back": 3, "room_back": 2, "dice": 3,
        })
        self.assertEqual(sum(counts.values()), EXPECTED_TOTAL)

    def test_06_new_record_id_segments_start_after_evt(self):
        slots = asset_pipeline.collect_slots(asset_pipeline.load_content())
        counters = {}
        assigned = []
        for slot in slots:
            cat = asset_pipeline.FAMILIES[slot["family"]]["cat"]
            counters[cat] = counters.get(cat, 0) + 1
            assigned.append("P-%s-%03d" % (cat, counters[cat]))
        self.assertEqual(counters, {
            "CHR": 12, "ROOM": 50, "OMEN": 13, "ITEM": 22, "EVT": 45,
            "MONS": 52, "HAUNT": 70, "END": 2, "CBACK": 3, "RBACK": 2, "DICE": 3,
        })
        rows = read_json()["records"]
        self.assertEqual(len(rows), EXPECTED_TOTAL)
        # 既有 142 位（CHR..EVT）的 record_id 与声明顺序完全不变
        self.assertEqual(assigned[:142], [row["record_id"] for row in rows[:142]])
        # 全表顺序一致：新六类段号接在 EVT 之后，不从 001 重排旧段
        self.assertEqual(assigned, [row["record_id"] for row in rows])
        self.assertEqual(assigned.index("P-MONS-001"), 142)
        self.assertEqual(assigned[142:145],
                         ["P-MONS-001", "P-MONS-002", "P-MONS-003"])
        self.assertEqual(assigned[-3:], ["P-DICE-001", "P-DICE-002", "P-DICE-003"])

    def test_07_collect_slots_tolerates_legacy_content_module(self):
        import types

        stub = types.SimpleNamespace(
            CHARACTER_FACES=[{"card_id": "card_1", "face_index": 1,
                              "id": "card_1_1", "name": "背面", "source_name": "back"}],
            ROOM_BASES=[{"id": "entrance_hall", "name": "门厅",
                         "source_name": "hall", "effect_id": ""}],
            # 3 元组：旧形态补充房间位没有 effect_id
            ROOM_SUPPLEMENTAL_SPECS=[("room_legacy", "旧房间", "legacy")],
            OMEN_CARDS=[], ITEM_CARDS=[], EVENT_BASES=[],
            EVENT_SUPPLEMENTAL_SPECS=[("event_legacy", "旧事件", "legacy", "effect")],
            RENDER_SURFACE_SPECS=[
                {"id": "ending_heroes", "name": "英雄胜利", "surface": "ending"},
                {"id": "card_back_omen", "name": "预兆牌背", "surface": "card_back"},
                {"id": "room_back", "name": "未翻地块", "surface": "room_back"},
                {"id": "room_ghost", "name": "落点虚影", "surface": "room_back"},
                {"id": "dice_0", "name": "骰面 0", "surface": "dice"},
            ],
        )
        stub.build_catalog = lambda seed=0: types.SimpleNamespace(haunt_defs={})
        slots = asset_pipeline.collect_slots(stub)
        self.assertEqual([slot["family"] for slot in slots],
                         ["character", "room", "room", "event",
                          "ending", "card_back", "room_back", "room_back", "dice"])
        self.assertEqual(slots[0]["semantic_hint"], "角色面：card_1 背面（back）")
        self.assertEqual(slots[2]["effect_id"], "", "旧 3 元组没有 effect_id")
        self.assertEqual([slot["runtime_key"] for slot in slots[4:]],
                         ["ending:heroes", "card_back:omen", "room_back:back",
                          "room_back:ghost", "dice:0"])

        # 完全没有 MONSTER_BASES / RENDER_SURFACE_SPECS 的旧 content 模块不抛异常
        del stub.RENDER_SURFACE_SPECS
        legacy = asset_pipeline.collect_slots(stub)
        self.assertEqual([slot["family"] for slot in legacy],
                         ["character", "room", "room", "event"])

    def test_08_runtime_rel_path_six_extra_dirs(self):
        for family, (_, dir_name) in EXTRA_RUNTIME_SPECS.items():
            slot = {"family": family, "runtime_name": "%s_probe" % family}
            rel = asset_pipeline.runtime_rel_path(slot)
            self.assertEqual(rel.parent, asset_pipeline.RUNTIME_EXTRA_DIRS[family], family)
            self.assertEqual(rel.name, "%s_probe.png" % family)
            self.assertTrue(
                str(rel).replace("\\", "/").endswith("/assets/%s/%s_probe.png"
                                                     % (dir_name, family)),
                str(rel))
        with self.assertRaises(ValueError):
            asset_pipeline.runtime_rel_path({"family": "unknown", "runtime_name": "x"})

    def test_09_normalize_assets_dispatches_extra_family(self):
        from PIL import Image

        root = Path(tempfile.mkdtemp(prefix="ptable_norm_root_"))
        self.addCleanup(shutil.rmtree, str(root), True)
        photos = root / "photos"
        self._make_image(photos / "monster" / "mummy.png", (64, 32), (1, 2, 3))
        target = root / "assets" / "monsters" / "mummy.png"
        records = [{
            "record_id": "P-MONS-001",
            "target_ref": "content.py:MONSTER_BASES#mummy",
            "runtime_path": "assets/monsters/mummy.png",
            "source_path": "photos/monster/mummy.png",
            "availability": "usable",
            "_family": "monster",
            "_runtime_abs": target,
        }]
        with mock.patch.object(asset_pipeline, "PROJECT_ROOT", root), \
                mock.patch.object(asset_pipeline, "PHOTOS_DIR", photos):
            result = asset_pipeline.normalize_assets(records)
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["written"], 1)
        with Image.open(target) as out:
            self.assertEqual(out.size, asset_pipeline.MONSTER_SIZE)
            self.assertEqual(out.mode, "RGBA")

        # 目标落回 photos/ 时必须拒绝写入（源目录只读）
        records[0]["_runtime_abs"] = photos / "monster" / "evil.png"
        with mock.patch.object(asset_pipeline, "PROJECT_ROOT", root), \
                mock.patch.object(asset_pipeline, "PHOTOS_DIR", photos):
            blocked = asset_pipeline.normalize_assets(records)
        self.assertEqual(blocked["written"], 0)
        self.assertIn("拒绝写入 photos", blocked["failures"][0]["reason"])
        self.assertFalse((photos / "monster" / "evil.png").exists())

        # 卡牌类仍走 normalize_card（六类之外的老分派），不能被 extra 分支吞掉
        self._make_image(photos / "omen" / "omen_probe.png", (1773, 2364), (9, 8, 7))
        card_target = root / "assets" / "cards" / "omen" / "omen_probe.png"
        card_records = [{
            "record_id": "P-OMEN-001",
            "target_ref": "content.py:OMEN_CARDS#omen_probe",
            "runtime_path": "assets/cards/omen/omen_probe.png",
            "source_path": "photos/omen/omen_probe.png",
            "availability": "usable",
            "_family": "omen",
            "_runtime_abs": card_target,
        }]
        with mock.patch.object(asset_pipeline, "PROJECT_ROOT", root), \
                mock.patch.object(asset_pipeline, "PHOTOS_DIR", photos):
            card_result = asset_pipeline.normalize_assets(card_records)
        self.assertEqual(card_result["failures"], [])
        with Image.open(card_target) as out:
            self.assertEqual(out.size, asset_pipeline.CARD_SIZE)

    def test_10_main_placeholders_stage_builds_three_files(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = asset_pipeline.main(["--stage", "placeholders"])
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("[placeholders] 3 张", buffer.getvalue())
        for kind in asset_pipeline.PLACEHOLDER_FILES:
            path = asset_pipeline.placeholder_path(kind)
            self.assertTrue(path.is_file(), path)
            data = path.read_bytes()
            self.assertTrue(data.startswith(PNG_SIGNATURE), kind)

    def test_11_assign_fallback_refs_resolves_and_rejects(self):
        records = [
            {"record_id": "P-EVT-001", "runtime_key": "card:event:target_row"},
            {"record_id": "P-EVT-002", "runtime_key": "card:event:source_row",
             "_fallback_target": "card:event:target_row"},
            {"record_id": "P-EVT-003", "runtime_key": "card:event:plain_row"},
        ]
        asset_pipeline.assign_fallback_refs(records)
        self.assertEqual(records[1]["fallback_ref"], "P-EVT-001")
        self.assertEqual(records[2]["fallback_ref"], "")
        broken = [{"record_id": "P-EVT-004", "runtime_key": "card:event:broken",
                   "_fallback_target": "card:event:absent"}]
        with self.assertRaises(SystemExit):
            asset_pipeline.assign_fallback_refs(broken)


# ----------------------------------------------------------------------
# 12. run6 六类渲染面：registry 映射 / 键空间 / 索引（asset_registry 侧）
# ----------------------------------------------------------------------
class TestRegistryRenderSurfaces(unittest.TestCase):
    """SPEC_BY_TYPE 六类映射、RECORD_ID_RE 扩展、键注册与三级索引回退。"""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="ptable_registry_"))
        self.addCleanup(shutil.rmtree, str(self.directory), True)

    def _write_manifest(self, name, payload):
        path = self.directory / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_01_spec_by_type_covers_six_surfaces(self):
        registry = load_registry()
        rows_by_type = {}
        for row in read_json()["records"]:
            if row["asset_type"] in EXTRA_RUNTIME_SPECS:
                rows_by_type.setdefault(row["asset_type"], row)
        for asset_type, (size, _) in EXTRA_RUNTIME_SPECS.items():
            self.assertEqual(asset_registry.SPEC_BY_TYPE.get(asset_type), asset_type)
            spec = asset_registry.SPEC_BY_TYPE[asset_type]
            self.assertIn(spec, registry.runtime_specs)
            raw = registry.runtime_specs[spec]
            self.assertEqual((raw["width"], raw["height"]), size)
            ref = registry.resolve(rows_by_type[asset_type]["record_id"])
            self.assertIsNotNone(ref, asset_type)
            self.assertEqual((ref.width, ref.height), size, asset_type)

    def test_02_record_id_re_accepts_new_prefixes(self):
        accepted = ["P-MONS-001", "P-HAUNT-070", "P-END-002",
                    "P-CBACK-003", "P-RBACK-002", "P-DICE-003"]
        for value in accepted:
            self.assertTrue(asset_registry.RECORD_ID_RE.match(value), value)
        for value in ("P-XXXX-001", "P-MONSTER-001", "P-MONS-1",
                      "P-MONS-0001", "p-mons-001", "P-MONS-001-x"):
            self.assertIsNone(asset_registry.RECORD_ID_RE.match(value), value)
        registry = load_registry()
        self.assertIsNotNone(registry.resolve("P-MONS-001"))
        self.assertIsNone(registry.resolve("P-XXXX-001"))

    def test_03_duplicate_registration_key_rejected(self):
        records = [
            {"record_id": "P-ROOM-001", "target_ref": "content.py:ROOM_BASES#dup",
             "runtime_key": "room:a", "asset_type": "room"},
            {"record_id": "P-ROOM-002", "target_ref": "content.py:ROOM_BASES#dup",
             "runtime_key": "room:b", "asset_type": "room"},
        ]
        with self.assertRaises(ValueError):
            AssetRegistry(records=records, runtime_specs={}, base_dir_name="",
                          project_root=str(PROJECT_ROOT), manifest_path="")

    def test_04_same_ref_registered_under_same_key(self):
        records = [{"record_id": "P-DICE-001", "target_ref": "dice:0",
                    "runtime_key": "dice:0", "asset_type": "dice"}]
        registry = AssetRegistry(
            records=records,
            runtime_specs={"dice": {"width": 256, "height": 256, "format": "png"}},
            base_dir_name="", project_root=str(PROJECT_ROOT), manifest_path="")
        # target_ref 与 runtime_key 相同：同一 AssetRef 重复注册不得报错
        self.assertEqual(len(registry), 1)
        self.assertIs(registry._refs["dice:0"], registry._refs["P-DICE-001"])
        self.assertEqual((registry.resolve("P-DICE-001").width,
                          registry.resolve("P-DICE-001").height), (256, 256))

    def test_05_legacy_content_refs_index_bare_ids(self):
        payload = {
            "base_dir": "game",
            "runtime_specs": {"card": {"width": 480, "height": 672, "format": "png"}},
            "records": [
                {"record_id": "P-OMEN-001",
                 "target_ref": "content.py:OMEN_CARDS#omen_bite",
                 "runtime_key": "card:omen:omen_bite", "asset_type": "card_omen"},
                {"record_id": "P-OMEN-002",
                 "target_ref": "content.py:OMEN_CARDS#omen_mask",
                 "runtime_key": "card:omen:omen_mask", "asset_type": "card_omen"},
                {"record_id": "P-ROOM-001",
                 "target_ref": "content.py:ROOM_BASES#entrance_hall",
                 "runtime_key": "", "asset_type": "room"},
                {"record_id": "P-ROOM-002",
                 "target_ref": "legacy:bare_only", "asset_type": "room"},
                {"record_id": "P-CHR-001",
                 "target_ref": "content.py:CHARACTER_FACES#card_1@f0",
                 "runtime_key": "card_1@f0", "asset_type": "character"},
            ],
            # 旧表/合成样本的 content_refs 反向表：content.py: -> 运行时键
            "content_refs": {
                "content.py:OMEN_CARDS#omen_bite": "card:omen:omen_bite",
                "content.py:OMEN_CARDS#omen_gap": "card:omen:absent_key",
            },
        }
        manifest = self._write_manifest("p_table.json", payload)
        registry = AssetRegistry.load(manifest, base_dir=str(self.directory))
        # 没有 content_ref 列时按 content_refs 反向表补内容侧入口
        self.assertEqual(registry.resolve("content.py:OMEN_CARDS#omen_bite").record_id,
                         "P-OMEN-001")
        self.assertEqual(registry.resolve("omen_bite").record_id, "P-OMEN-001")
        # 反向表指向不存在的运行时键：跳过，不建错误索引
        self.assertIsNone(registry.resolve("content.py:OMEN_CARDS#omen_gap"))
        # 裸 id 三级回退：runtime_key 缺失时用 target_ref 末段
        self.assertEqual(registry.resolve("bare_only").record_id, "P-ROOM-002")
        # runtime_key 为空时裸 id 由 target_ref 的 id 段补上（第二级索引）
        self.assertEqual(registry.resolve("entrance_hall").record_id, "P-ROOM-001")
        # 角色裸键走 runtime_key（face 后缀），不被裸 id 规则改名
        self.assertEqual(registry.resolve("card_1@f0").record_id, "P-CHR-001")

    def test_06_load_falls_back_to_sibling_p_table(self):
        payload = {"base_dir": "", "records": [
            {"record_id": "P-DICE-001", "target_ref": "dice:0",
             "runtime_key": "dice:0", "asset_type": "dice"}]}
        self._write_manifest("p_table.json", payload)
        manifest = self._write_manifest("asset_mapping.json", {"base_dir": ""})
        registry = AssetRegistry.load(manifest, base_dir=str(self.directory))
        self.assertIsNotNone(registry.resolve("P-DICE-001"))
        self.assertEqual(registry.manifest_path.name, "p_table.json")

    def test_07_load_reports_missing_and_records_absent(self):
        with self.assertRaises(FileNotFoundError):
            AssetRegistry.load(self.directory / "no_such_manifest.json")
        lonely = self._write_manifest("lonely.json", {"base_dir": ""})
        with self.assertRaises(ValueError):
            AssetRegistry.load(lonely, base_dir=str(self.directory))

    def test_08_detect_project_root_fallbacks(self):
        base = Path(tempfile.mkdtemp(prefix="ptable_root_"))
        self.addCleanup(shutil.rmtree, str(base), True)
        # 打包布局：没有 photos，但有 source/desktop/game/assets
        packed = base / "app"
        packed_assets = packed / "source" / "desktop" / "game" / "assets"
        packed_assets.mkdir(parents=True)
        packed_manifest = packed_assets / "p_table.json"
        packed_manifest.write_text("{}", encoding="utf-8")
        self.assertEqual(
            AssetRegistry._detect_project_root(packed_manifest, "", None),
            packed.resolve())
        # 只有 base_dir_name 命中祖先目录名
        named = base / "portable" / "inner" / "assets"
        named.mkdir(parents=True)
        named_manifest = named / "p_table.json"
        named_manifest.write_text("{}", encoding="utf-8")
        self.assertEqual(
            AssetRegistry._detect_project_root(named_manifest, "portable", None),
            (base / "portable").resolve())
        # 三个特征都没有：退回祖先第 5 层，不抛异常
        deep = base / "a" / "b" / "c" / "d" / "e" / "f" / "assets"
        deep.mkdir(parents=True)
        deep_manifest = deep / "p_table.json"
        deep_manifest.write_text("{}", encoding="utf-8")
        detected = AssetRegistry._detect_project_root(deep_manifest, "", None)
        self.assertIsInstance(detected, Path)
        self.assertTrue(detected.is_dir())

    def test_09_defaults_without_project_root_or_manifest(self):
        registry = AssetRegistry(records=[], runtime_specs=None, base_dir_name="",
                                 project_root=None, manifest_path=None)
        self.assertEqual(registry.project_root, Path.cwd())
        self.assertIsNone(registry.manifest_path)
        self.assertEqual(registry.runtime_specs, {})
        self.assertEqual(len(registry), 0)
        self.assertEqual(registry.summary(), {
            "records": 0, "availability": {}, "runtime_status": {}})

    def test_10_asset_ref_exists_and_validate_without_root(self):
        self.assertFalse(asset_registry.AssetRef(record_id="P-ROOM-001", path="").exists())
        real = first_row("room")["runtime_path"]
        self.assertTrue(asset_registry.AssetRef(
            record_id="P-ROOM-001", path=str(PROJECT_ROOT / real)).exists())
        # assets_root=None：不校验越界，其余判定照旧（当前 0 missing -> 无 issue）
        self.assertEqual(load_registry().validate(), [])

    def test_11_png_size_rejects_non_png_input(self):
        self.assertIsNone(asset_registry.png_size(self.directory))
        broken = self.directory / "broken.png"
        broken.write_bytes(PNG_SIGNATURE + b"\x00\x00")
        self.assertIsNone(asset_registry.png_size(broken))

    def test_12_resolve_manifest_path_falls_back_to_first_candidate(self):
        missing = [self.directory / "a.json", self.directory / "b.json"]
        with mock.patch.object(asset_registry, "default_manifest_candidates",
                               return_value=missing):
            self.assertEqual(asset_registry.resolve_manifest_path(), missing[0])
        with mock.patch.object(asset_registry, "default_manifest_candidates",
                               return_value=[missing[0], MAPPING_JSON]):
            self.assertEqual(asset_registry.resolve_manifest_path(), MAPPING_JSON)

    def test_13_missing_and_by_type_listings(self):
        registry = load_registry()
        self.assertEqual(registry.missing(), [])
        self.assertEqual(len(registry.by_type("monster")), 52)
        self.assertEqual(len(registry.by_type("haunt")), 70)
        self.assertEqual(registry.by_type("no_such_type"), [])
        self.assertEqual(len(asset_registry.load_registry(PTABLE_JSON, str(PROJECT_ROOT))),
                         EXPECTED_TOTAL)

    def test_15_indexes_skip_empty_content_and_target_ids(self):
        payload = {
            "base_dir": "",
            "runtime_specs": {"room": {"width": 512, "height": 512, "format": "png"}},
            "records": [
                # content_ref 的 "#" 后为空：内容侧不建索引
                {"record_id": "P-ROOM-001", "asset_type": "room",
                 "target_ref": "content.py:ROOM_BASES#room_a",
                 "runtime_key": "room:room_a",
                 "content_ref": "content.py:ROOM_BASES#"},
                # target_ref 的 "#" 后为空：id 段索引跳过
                {"record_id": "P-ROOM-002", "asset_type": "room",
                 "target_ref": "content.py:ROOM_BASES#",
                 "runtime_key": "room:room_b",
                 "content_ref": "content.py:ROOM_BASES#room_b"},
            ],
            # 反向表里 "#" 后为空：裸 id 建不出来，只能建内容侧入口
            "content_refs": {"content.py:ROOM_BASES#": "room:room_a"},
        }
        manifest = self._write_manifest("p_table.json", payload)
        registry = AssetRegistry.load(manifest, base_dir=str(self.directory))
        # target_ref 本身就是键：空 id 的 target_ref 仍按原样注册（不自作聪明截断）
        self.assertEqual(registry.resolve("content.py:ROOM_BASES#").record_id,
                         "P-ROOM-002")
        self.assertEqual(registry.resolve("room_a").record_id, "P-ROOM-001")
        self.assertEqual(registry.resolve("room_b").record_id, "P-ROOM-002")
        self.assertEqual(registry.resolve("content.py:ROOM_BASES#room_a").record_id,
                         "P-ROOM-001")
        # 空串不得进键空间（否则会解析出未定义的资源位）
        self.assertNotIn("", registry._refs)

    def test_16_project_root_base_dir_scan_exhausts_without_match(self):
        base = Path(tempfile.mkdtemp(prefix="ptable_root_scan_"))
        self.addCleanup(shutil.rmtree, str(base), True)
        assets = base / "alpha" / "beta" / "assets"
        assets.mkdir(parents=True)
        manifest = assets / "p_table.json"
        manifest.write_text("{}", encoding="utf-8")
        detected = AssetRegistry._detect_project_root(manifest, "no_such_dir_name", None)
        self.assertIsInstance(detected, Path)
        self.assertTrue(detected.is_dir())

    def test_14_key_space_rejects_traversal_and_unknown_faces(self):
        registry = load_registry()
        for key in ("card_999#f0", "room:..\\escape", "content.py:ROOM_BASES#../etc"):
            self.assertIsNone(registry.resolve(key), key)
        self.assertEqual(registry.resolve("card_1#f0").record_id,
                         registry.resolve("character:card_1:f0").record_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
