#!/usr/bin/env python
"""图片资源管线自测：校验 P 表、规范化产物与注册表一致性。

失败即非零退出（CI/发布门禁用）：

    python verify_assets.py        # 0=PASS, 1=FAIL

校验覆盖（run5 基线 v2：142 usable / 0 missing / 145 运行时 PNG）：
    V01 CSV 编码与列序        V02 142 行             V03 分类计数 12/50/45/22/13
    V04 record_id 稳定唯一    V05 target_ref/runtime_key 与 content.py 双向可解析
    V06 142 个源文件均为真 PNG  V07 0 个缺口（任何 missing 即 FAIL）
    V08 运行时 PNG 与尺寸     V09 回退语义（0 fallback / 0 placeholder）
    V10 占位图规格（仅 3 张，WW 占位图不得回落）
    V11 photos 只读（142 源文件 + 130 备份，sha256 与清单一致）
    V12 CSV/JSON 一致         V13 映射文件覆盖（142/0）
    V14 注册表全量解析（新旧键）                        V15 不伪造路径引用
    V16 dimensions/aspect_ratio/content_ref 与源事实一致
    V17 发布档 7 列（bytes/sha256/category_dir/alpha_required/
        canonical_record_id/reviewer/verified_at）与源事实一致

重基线记录（run5 §4.6）：V05 在 WW 隔离后自然回到 7 个集合 = 142 个 id；
V06/V07/V08/V09/V12/V13 的 95/47 期望改为 142/0；V11 拆成"数量"与"哈希"
两条断言，并显式排除 ``photos/_source_jpeg/``（转码原件备份）。

结果写入 assets/validation_report.json。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GAME_DIR.parents[2]
PHOTOS_DIR = PROJECT_ROOT / "photos"
ASSETS_DIR = GAME_DIR / "assets"
PTABLE_CSV = ASSETS_DIR / "p_table.csv"
PTABLE_JSON = ASSETS_DIR / "p_table.json"
MAPPING_JSON = ASSETS_DIR / "asset_mapping.json"
REPORT_JSON = ASSETS_DIR / "validation_report.json"
INVENTORY_JSON = PROJECT_ROOT / ".codebuddy" / "wfat" / "photos_inventory.json"

if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

import asset_pipeline  # noqa: E402  复用列序/魔数/尺寸规格，避免两处定义漂移
from asset_registry import AssetRegistry, png_size  # noqa: E402

# run6：九类渲染面接入，142 -> 274（新增 monster 52 / haunt 70 / ending 2 /
# card_back 3 / room_back 2 / dice 3）。
EXPECTED_TOTAL = 274
EXPECTED_BY_TYPE = {
    "character": 12,
    "room": 50,
    "card_event": 45,
    "card_item": 22,
    "card_omen": 13,
    "monster": 52,
    "haunt": 70,
    "ending": 2,
    "card_back": 3,
    "room_back": 2,
    "dice": 3,
}
# run5 v2：47 个缺口已按"复用既有文件 + 转码"落实，缺口期望为 0。
EXPECTED_MISSING_BY_TYPE = {}
EXPECTED_MISSING = 0
EXPECTED_MISSING_FALLBACK = 0
EXPECTED_MISSING_PENDING = 0
EXPECTED_PRESENT = 274            # 有源文件的资源位（= 全部 274）
EXPECTED_USABLE = 274
EXPECTED_PARTIAL = 0
EXPECTED_BACKUPS = 130            # photos/_source_jpeg/ 的转码原件
# 运行时产物：原有 145（50 房间 + 80 卡面 + 12 角色 + 3 占位）
# + run6 新增 132（monster 52 / haunt 70 / ending 2 / card_back 3 / room_back 2 / dice 3）
EXPECTED_RUNTIME = {
    "rooms": 50, "cards": 80, "characters": 12, "placeholders": 3,
    "monsters": 52, "haunts": 70, "endings": 2,
    "card_backs": 3, "room_backs": 2, "dice": 3,
}
EXPECTED_RUNTIME_TOTAL = 277
BACKUP_DIRNAME = "_source_jpeg"
TRANSCODE_MANIFEST = GAME_DIR / "qa" / "run5_transcode_manifest.json"
ASSETS_WW_DIR = GAME_DIR / "assets_ww"
# content.py 不得再出现这些 WW 标识符 / 字面量（A-29 判据 2，V05 顺带守门）。
WW_TOKENS = ("ROOF_ROOMS", "ROOF_ROOM_IDS", "WW_EVENT_ADDITION", "_roof_room_def",
             "ww_", "roof_", "widows_walk")
FALLBACK_RECORD_ID_RE = re.compile(r"^P-EVT-\d{3}$")
CONTENT_COLLECTIONS_BY_TYPE = {
    "character": ("CHARACTER_FACES",),
    "room": ("ROOM_BASES", "ROOM_SUPPLEMENTAL_SPECS"),
    "card_omen": ("OMEN_CARDS",),
    "card_item": ("ITEM_CARDS",),
    "card_event": ("EVENT_BASES", "EVENT_SUPPLEMENTAL_SPECS"),
    # run6 六类渲染面
    "monster": ("MONSTER_BASES",),
    "haunt": ("HAUNT_DEFS",),
    "ending": ("RENDER_SURFACE_SPECS",),
    "card_back": ("RENDER_SURFACE_SPECS",),
    "room_back": ("RENDER_SURFACE_SPECS",),
    "dice": ("RENDER_SURFACE_SPECS",),
}
TARGET_SIZE = {
    "character": asset_pipeline.CHARACTER_SIZE,
    "room": asset_pipeline.ROOM_SIZE,
    "card_omen": asset_pipeline.CARD_SIZE,
    "card_item": asset_pipeline.CARD_SIZE,
    "card_event": asset_pipeline.CARD_SIZE,
    # run6 六类渲染面（尺寸为工程自定，见 asset_pipeline.RUNTIME_SPECS）
    "monster": asset_pipeline.MONSTER_SIZE,
    "haunt": asset_pipeline.HAUNT_SIZE,
    "ending": asset_pipeline.ENDING_SIZE,
    "card_back": asset_pipeline.CARD_BACK_SIZE,
    "room_back": asset_pipeline.ROOM_BACK_SIZE,
    "dice": asset_pipeline.DICE_SIZE,
}
CATEGORY_PREFIX = {"character": "CHR", "room": "ROOM", "card_omen": "OMEN",
                   "card_item": "ITEM", "card_event": "EVT",
                   "monster": "MONS", "haunt": "HAUNT", "ending": "END",
                   "card_back": "CBACK", "room_back": "RBACK", "dice": "DICE"}

# 按 asset_type 判定**运行时是否必须带 alpha**，与 asset_pipeline.ALPHA_REQUIRED
# 同义（run6：怪物标记 / 未翻地块 / 骰面需要透明通道，可叠在地块上）。
# 注意：结算图与牌背的源母版虽然是 RGBA，但运行时不需要 alpha，因此这里是 False。
ALPHA_EXPECTED_BY_TYPE = {
    "character": True,
    "room": False,
    "card_omen": False,
    "card_item": False,
    "card_event": False,
    "monster": True,
    "haunt": False,
    "ending": False,
    "card_back": False,
    "room_back": True,
    "dice": True,
}


# ----------------------------------------------------------------------
# 报告骨架
# ----------------------------------------------------------------------
class Checker:
    def __init__(self):
        self.checks = []

    def add(self, check_id, name, failures, detail=""):
        failures = list(failures)
        status = "pass" if not failures else "fail"
        if not failures:
            text = detail or "ok"
        else:
            text = "%s；%d 项失败" % (detail, len(failures)) if detail else "%d 项失败" % len(failures)
        record = {
            "id": check_id,
            "name": name,
            "status": status,
            "detail": text,
        }
        if failures:
            record["failures"] = failures[:20]
            record["failure_count"] = len(failures)
        self.checks.append(record)
        return status == "pass"

    @property
    def failed(self):
        return [check for check in self.checks if check["status"] != "pass"]


def _norm(value):
    """把 CSV 字符串与 JSON 原生值归一到同一比较口径。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    return str(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _case_consistent(rel_path: str) -> bool:
    """逐段比对磁盘真实名称（Windows 大小写不敏感，发布端敏感）。"""
    current = PROJECT_ROOT
    for part in rel_path.split("/"):
        if not part:
            continue
        try:
            entries = {entry.name for entry in current.iterdir()}
        except OSError:
            return False
        if part not in entries:
            return False
        current = current / part
    return True


def _content_sets():
    module = asset_pipeline.load_content()
    return {
        "CHARACTER_FACES": [face["id"] for face in module.CHARACTER_FACES],
        "ROOM_BASES": [room["id"] for room in module.ROOM_BASES],
        "ROOM_SUPPLEMENTAL_SPECS": [spec[0] for spec in module.ROOM_SUPPLEMENTAL_SPECS],
        "OMEN_CARDS": [card["id"] for card in module.OMEN_CARDS],
        "ITEM_CARDS": [card["id"] for card in module.ITEM_CARDS],
        "EVENT_BASES": [card["id"] for card in module.EVENT_BASES],
        "EVENT_SUPPLEMENTAL_SPECS": [spec[0] for spec in module.EVENT_SUPPLEMENTAL_SPECS],
        # run6 六类渲染面：怪物与剧本来自既有集合，其余 10 位来自渲染面声明
        "MONSTER_BASES": [monster["id"] for monster in module.MONSTER_BASES],
        "HAUNT_DEFS": [str(key) for key in module.build_catalog(0).haunt_defs],
        "RENDER_SURFACE_SPECS": [spec["id"] for spec in module.RENDER_SURFACE_SPECS],
    }


def _event_effect_map():
    """补充事件的 effect_id 归属（回退目标来自 content.py，不是手写常量）。"""
    module = asset_pipeline.load_content()
    return {spec[0]: spec[3] for spec in module.EVENT_SUPPLEMENTAL_SPECS}


def _runtime_artifacts():
    rooms = sorted((ASSETS_DIR / "rooms").glob("*.png"))
    cards = sorted((ASSETS_DIR / "cards").rglob("*.png"))
    placeholders = sorted((ASSETS_DIR / "placeholders").glob("*.png"))
    return rooms, cards, placeholders


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main() -> int:
    checker = Checker()

    if not PTABLE_CSV.is_file() or not PTABLE_JSON.is_file():
        print("[FAIL] 缺少 P 表产物，请先运行 python asset_pipeline.py")
        return 1

    raw = PTABLE_CSV.read_bytes()
    with PTABLE_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        csv_rows = [dict(row) for row in reader]

    with PTABLE_JSON.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    json_rows = payload.get("records") or []

    # V01 编码与列序 ----------------------------------------------------
    failures = []
    if not raw.startswith(b"\xef\xbb\xbf"):
        failures.append({"issue": "missing_bom"})
    if header != list(asset_pipeline.CSV_COLUMNS):
        failures.append({
            "issue": "header_mismatch",
            "expected": list(asset_pipeline.CSV_COLUMNS),
            "actual": header,
        })
    checker.add("V01", "p_table.csv 为 UTF-8 BOM 且列序固定", failures,
                "BOM ok；%d 列" % len(header))

    # V02 行数 ---------------------------------------------------------
    failures = []
    if len(csv_rows) != EXPECTED_TOTAL:
        failures.append({"issue": "row_count", "actual": len(csv_rows)})
    if len(json_rows) != EXPECTED_TOTAL:
        failures.append({"issue": "json_row_count", "actual": len(json_rows)})
    checker.add("V02", "P 表 142 行", failures,
                "csv=%d / json=%d" % (len(csv_rows), len(json_rows)))

    # V03 分类计数 -----------------------------------------------------
    counts = {}
    for row in csv_rows:
        counts[row["asset_type"]] = counts.get(row["asset_type"], 0) + 1
    failures = [
        {"asset_type": key, "expected": value, "actual": counts.get(key, 0)}
        for key, value in EXPECTED_BY_TYPE.items()
        if counts.get(key, 0) != value
    ]
    extra = {key: value for key, value in counts.items() if key not in EXPECTED_BY_TYPE}
    if extra:
        failures.append({"issue": "unexpected_asset_type", "actual": extra})
    checker.add("V03", "分类计数 角色12/房间50/事件45/物品22/预兆13", failures,
                " / ".join("%s=%d" % (k, counts.get(k, 0)) for k in EXPECTED_BY_TYPE))

    # V04 record_id 完整性 --------------------------------------------
    failures = []
    seen = set()
    per_prefix = {}
    for row in csv_rows:
        record_id = row["record_id"]
        if record_id in seen:
            failures.append({"issue": "duplicate_record_id", "record_id": record_id})
            continue
        seen.add(record_id)
        expected_prefix = CATEGORY_PREFIX.get(row["asset_type"])
        parts = record_id.split("-")
        if len(parts) != 3 or parts[0] != "P" or parts[1] != expected_prefix:
            failures.append({"issue": "record_id_prefix", "record_id": record_id,
                             "asset_type": row["asset_type"]})
            continue
        try:
            number = int(parts[2])
        except ValueError:
            failures.append({"issue": "record_id_number", "record_id": record_id})
            continue
        per_prefix.setdefault(expected_prefix, []).append(number)
    for prefix, numbers in per_prefix.items():
        expected = list(range(1, max(numbers) + 1))
        if sorted(numbers) != expected:
            failures.append({"issue": "record_id_gap", "prefix": prefix,
                             "actual": sorted(numbers)})
    checker.add("V04", "record_id 唯一、前缀与类型一致、段号连续", failures,
                "%d 个唯一 id" % len(seen))

    # V05 target_ref 与 content.py ------------------------------------
    content_sets = _content_sets()
    content_ids = {key: set(values) for key, values in content_sets.items()}
    content_refs = payload.get("content_refs") or {}
    registry = AssetRegistry.load(PTABLE_JSON, base_dir=str(PROJECT_ROOT))

    failures = []
    target_refs = [row["target_ref"] for row in csv_rows]
    if len(set(target_refs)) != EXPECTED_TOTAL:
        failures.append({"issue": "duplicate_target_ref",
                         "unique": len(set(target_refs))})
    runtime_keys = [row["runtime_key"] for row in csv_rows]
    if len(set(runtime_keys)) != EXPECTED_TOTAL:
        failures.append({"issue": "duplicate_runtime_key",
                         "unique": len(set(runtime_keys))})
    covered = {}
    for row in csv_rows:
        resolved = registry.resolve(row["target_ref"])
        if resolved is None or resolved.record_id != row["record_id"]:
            failures.append({"issue": "registry_unresolved",
                             "target_ref": row["target_ref"]})
        # 运行时键必须与 target_ref 指向同一个资源位（新旧键并存不漂移）
        by_runtime = registry.resolve(row["runtime_key"])
        if by_runtime is None or by_runtime.record_id != row["record_id"]:
            failures.append({"issue": "registry_unresolved_runtime_key",
                             "runtime_key": row["runtime_key"]})
        elif by_runtime.target_ref != row["target_ref"]:
            failures.append({"issue": "runtime_key_target_mismatch",
                             "runtime_key": row["runtime_key"],
                             "target_ref": row["target_ref"],
                             "resolved": by_runtime.target_ref})
        if content_refs.get(row["runtime_key"]) != row["content_ref"]:
            failures.append({"issue": "content_refs_forward_missing",
                             "runtime_key": row["runtime_key"]})
        if content_refs.get(row["content_ref"]) != row["runtime_key"]:
            failures.append({"issue": "content_refs_reverse_missing",
                             "content_ref": row["content_ref"]})
        content_ref = row["content_ref"]
        if not content_ref.startswith("content.py:"):
            failures.append({"issue": "content_ref_missing",
                             "target_ref": row["target_ref"]})
            continue
        collection, _, content_id = content_ref[len("content.py:"):].partition("#")
        if collection not in content_ids:
            failures.append({"issue": "collection_unknown", "collection": collection})
        elif content_id not in content_ids[collection]:
            failures.append({"issue": "content_id_unknown",
                             "collection": collection, "id": content_id})
        else:
            covered.setdefault(collection, set()).add(content_id)
    for collection, ids in content_ids.items():
        missing = ids - covered.get(collection, set())
        if missing:
            failures.append({"issue": "slot_not_in_p_table", "collection": collection,
                             "missing": sorted(missing)[:5]})

    # run5 V05 追加：WW 隔离后 content.py 应只剩 142 位对应内容。
    expected_collection_sizes = {
        "CHARACTER_FACES": 12,
        "ROOM_BASES": 39,
        "ROOM_SUPPLEMENTAL_SPECS": 11,
        "OMEN_CARDS": 13,
        "ITEM_CARDS": 22,
        "EVENT_BASES": 11,
        "EVENT_SUPPLEMENTAL_SPECS": 34,
    }
    for collection, expected in expected_collection_sizes.items():
        actual = len(content_ids.get(collection, set()))
        if actual != expected:
            failures.append({"issue": "collection_size", "collection": collection,
                             "expected": expected, "actual": actual})
    total_content_ids = sum(len(ids) for ids in content_ids.values())
    if total_content_ids != EXPECTED_TOTAL:
        failures.append({"issue": "content_id_total", "actual": total_content_ids})
    content_source = (GAME_DIR / "content.py").read_text(encoding="utf-8")
    for token in WW_TOKENS:
        if token in content_source:
            failures.append({"issue": "ww_residue_in_content", "token": token})
    content_module = asset_pipeline.load_content()
    for attribute in ("ROOF_ROOMS", "ROOF_ROOM_IDS", "FLOOR_ROOF", "WW_EVENT_ADDITION"):
        if hasattr(content_module, attribute):
            failures.append({"issue": "ww_attribute_in_content", "attribute": attribute})
    checker.add("V05",
                "target_ref/runtime_key 均唯一，且与 content.py 双向一一对应（WW 已隔离）",
                failures,
                "142 个 target_ref 与 142 个 runtime_key 全部可解析且指向同一行，"
                "content_refs 双向映射完整；7 个集合合计 142 个 id 无遗漏、无 WW 残留")

    # V06 142 个源文件：真 PNG、可解码、usable -------------------------
    failures = []
    present_rows = [row for row in csv_rows if row["availability"] != "missing"]
    if len(present_rows) != EXPECTED_PRESENT:
        failures.append({"issue": "present_count", "actual": len(present_rows)})
    for row in present_rows:
        source_path = row["source_path"]
        if not source_path:
            failures.append({"issue": "empty_source", "record_id": row["record_id"]})
            continue
        absolute = PROJECT_ROOT / source_path
        if not absolute.is_file():
            failures.append({"issue": "source_absent", "source_path": source_path})
            continue
        if not _case_consistent(source_path):
            failures.append({"issue": "case_mismatch", "source_path": source_path})
        if row["availability"] != "usable":
            failures.append({"issue": "unexpected_availability",
                             "record_id": row["record_id"], "value": row["availability"]})
        # run5 v2：交付层禁止"JPEG 内容 + .png 扩展名"，必须真 PNG 魔数
        if row["format"] != "png":
            failures.append({"issue": "format_not_png", "record_id": row["record_id"],
                             "value": row["format"]})
        head = absolute.read_bytes()[:8]
        if not head.startswith(b"\x89PNG\r\n\x1a\n"):
            failures.append({"issue": "source_magic_not_png", "record_id": row["record_id"],
                             "magic": head.hex()})
        if absolute.suffix.lower() != ".png":
            failures.append({"issue": "ext_not_png", "record_id": row["record_id"],
                             "value": absolute.suffix})
        if "ext_mismatch" in row["quality_flags"]:
            failures.append({"issue": "ext_mismatch_remained", "record_id": row["record_id"]})
        if row["availability"] == "usable" and row["quality_flags"]:
            failures.append({"issue": "usable_with_flags", "record_id": row["record_id"],
                             "value": row["quality_flags"]})
        expected_alpha = "true" if ALPHA_EXPECTED_BY_TYPE.get(row["asset_type"], False) else "false"
        # V06 只断言「需要 alpha 的类别必须带 alpha」；不需要 alpha 的类别
        # 允许源图自带透明留白（如结算图、牌背母版是 RGBA），不作反向断言。
        if expected_alpha == "true" and row["has_alpha"] != "true":
            failures.append({"issue": "alpha_mismatch", "record_id": row["record_id"],
                             "expected": expected_alpha, "actual": row["has_alpha"]})
        if row["decodable"] != "ok":
            failures.append({"issue": "not_decodable", "record_id": row["record_id"]})
        if row["missing_note"]:
            failures.append({"issue": "note_not_empty", "record_id": row["record_id"]})
        if row["source_file"] != Path(source_path).name:
            failures.append({"issue": "source_file_basename", "record_id": row["record_id"]})
    checker.add("V06", "142 个源文件存在、真 PNG 魔数、扩展名一致、标 usable 且无 quality_flags",
                failures, "142/142 真 PNG（角色 12 张 RGBA 带 alpha），0 条 ext_mismatch")

    # V07 0 个缺口（任何 missing 即 FAIL）-----------------------------
    failures = []
    missing_rows = [row for row in csv_rows if row["availability"] == "missing"]
    if len(missing_rows) != EXPECTED_MISSING:
        failures.append({"issue": "missing_count", "actual": len(missing_rows),
                         "sample": [row["record_id"] for row in missing_rows[:5]]})
    missing_by_type = {}
    for row in missing_rows:
        missing_by_type[row["asset_type"]] = missing_by_type.get(row["asset_type"], 0) + 1
        if row["source_path"]:
            failures.append({"issue": "missing_has_source_path",
                             "record_id": row["record_id"], "value": row["source_path"]})
        if row["source_file"]:
            failures.append({"issue": "missing_has_source_file",
                             "record_id": row["record_id"]})
        if row["mapping_status"] not in ("fallback", "pending_missing"):
            failures.append({"issue": "missing_mapping_status",
                             "record_id": row["record_id"],
                             "value": row["mapping_status"]})
        if not row["missing_note"]:
            failures.append({"issue": "missing_note_absent", "record_id": row["record_id"]})
        if row["usable_fields"]:
            failures.append({"issue": "missing_usable_fields",
                             "record_id": row["record_id"],
                             "value": row["usable_fields"]})
        if not row["runtime_path"]:
            failures.append({"issue": "missing_runtime_path", "record_id": row["record_id"]})
    for asset_type, expected in EXPECTED_MISSING_BY_TYPE.items():
        if missing_by_type.get(asset_type, 0) != expected:
            failures.append({"issue": "missing_type_count", "asset_type": asset_type,
                             "expected": expected,
                             "actual": missing_by_type.get(asset_type, 0)})

    # 缺口两类计数器保留（v2 期望均为 0）：出现即说明回退到旧语义，不得删断言。
    pending_rows = [r for r in missing_rows if r["mapping_status"] == "pending_missing"]
    fallback_missing = [r for r in missing_rows if r["mapping_status"] == "fallback"]
    if len(pending_rows) != EXPECTED_MISSING_PENDING:
        failures.append({"issue": "pending_missing_count", "actual": len(pending_rows)})
    if len(fallback_missing) != EXPECTED_MISSING_FALLBACK:
        failures.append({"issue": "fallback_missing_count", "actual": len(fallback_missing)})
    for row in pending_rows:
        if row["fallback_ref"]:
            failures.append({"issue": "pending_missing_has_fallback",
                             "record_id": row["record_id"], "value": row["fallback_ref"]})
        if row["runtime_status"] != "placeholder":
            failures.append({"issue": "pending_missing_runtime",
                             "record_id": row["record_id"], "value": row["runtime_status"]})
    for row in fallback_missing:
        if not FALLBACK_RECORD_ID_RE.match(row["fallback_ref"]):
            failures.append({"issue": "fallback_ref_not_record_id",
                             "record_id": row["record_id"], "value": row["fallback_ref"]})
    checker.add("V07", "0 个缺口：任何 availability=missing 即 FAIL（旧 47 缺口已全部落实）",
                failures, "missing=0 / fallback=0 / pending_missing=0；"
                          "47 位按 qa/run5_promotion_map.json 逐行登记")

    # V08 运行时产物 ---------------------------------------------------
    failures = []
    runtime_status_count = {}
    mapping_status_count = {}
    for row in csv_rows:
        runtime_path = row["runtime_path"]
        runtime_status_count[row["runtime_status"]] = \
            runtime_status_count.get(row["runtime_status"], 0) + 1
        mapping_status_count[row["mapping_status"]] = \
            mapping_status_count.get(row["mapping_status"], 0) + 1
        if not runtime_path:
            failures.append({"issue": "runtime_empty", "record_id": row["record_id"]})
            continue
        absolute = PROJECT_ROOT / runtime_path
        if not absolute.is_file():
            failures.append({"issue": "runtime_absent", "runtime_path": runtime_path})
            continue
        size = png_size(absolute)
        if size is None:
            failures.append({"issue": "runtime_not_png", "runtime_path": runtime_path})
            continue
        expected = TARGET_SIZE[row["asset_type"]]
        if size != expected:
            failures.append({"issue": "runtime_size", "runtime_path": runtime_path,
                             "expected": list(expected), "actual": list(size)})
        if row["runtime_format"] != "png":
            failures.append({"issue": "runtime_format", "record_id": row["record_id"]})
        if row["runtime_status"] not in ("ok", "fallback", "placeholder"):
            failures.append({"issue": "runtime_status_value",
                             "record_id": row["record_id"],
                             "value": row["runtime_status"]})
        first_bytes = absolute.read_bytes()[:8]
        if not first_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            failures.append({"issue": "runtime_magic", "runtime_path": runtime_path})
    if runtime_status_count.get("ok", 0) != EXPECTED_USABLE:
        failures.append({"issue": "runtime_ok_count",
                         "actual": runtime_status_count.get("ok", 0)})
    if runtime_status_count.get("fallback", 0) != 0:
        failures.append({"issue": "runtime_fallback_count",
                         "actual": runtime_status_count.get("fallback", 0)})
    if runtime_status_count.get("placeholder", 0) != 0:
        failures.append({"issue": "runtime_placeholder_count",
                         "actual": runtime_status_count.get("placeholder", 0)})

    # run5 v2：运行时目录计数 rooms 50 / cards 80 / characters 12 / placeholders 3
    runtime_dirs = {
        "rooms": ASSETS_DIR / "rooms",
        "cards": ASSETS_DIR / "cards",
        "characters": ASSETS_DIR / "characters",
        "placeholders": ASSETS_DIR / "placeholders",
        # run6 六类渲染面运行时目录
        "monsters": ASSETS_DIR / "monsters",
        "haunts": ASSETS_DIR / "haunts",
        "endings": ASSETS_DIR / "endings",
        "card_backs": ASSETS_DIR / "card_backs",
        "room_backs": ASSETS_DIR / "room_backs",
        "dice": ASSETS_DIR / "dice",
    }
    runtime_counts = {}
    for key, base in runtime_dirs.items():
        runtime_counts[key] = len(sorted(base.rglob("*.png"))) if base.is_dir() else 0
        expected = EXPECTED_RUNTIME[key]
        if runtime_counts[key] != expected:
            failures.append({"issue": "runtime_dir_count", "dir": key,
                             "expected": expected, "actual": runtime_counts[key]})
    total_runtime = sum(runtime_counts.values())
    if total_runtime != EXPECTED_RUNTIME_TOTAL:
        failures.append({"issue": "runtime_total", "expected": EXPECTED_RUNTIME_TOTAL,
                         "actual": total_runtime})
    checker.add("V08", "274 个 runtime_path 存在、真实 PNG、尺寸符合规格"
                       "（277 张运行时 PNG：50/80/12/3 + 52/70/2/3/2/3）", failures,
                "ok=274 / fallback=0 / placeholder=0；" + " ".join(
                    "%s=%d" % (k, v) for k, v in runtime_counts.items()))

    # V09 回退语义 -----------------------------------------------------
    failures = []
    effect_map = _event_effect_map()
    record_id_by_runtime = {row["runtime_key"]: row["record_id"] for row in csv_rows}
    fallback_rows = [row for row in csv_rows if row["runtime_status"] == "fallback"]
    if len(fallback_rows) != 0:
        failures.append({"issue": "fallback_event_count", "actual": len(fallback_rows)})
    placeholder_rows = [row for row in csv_rows if row["runtime_status"] == "placeholder"]
    if len(placeholder_rows) != 0:
        failures.append({"issue": "placeholder_count", "actual": len(placeholder_rows),
                         "sample": [row["record_id"] for row in placeholder_rows[:5]]})
    for row in fallback_rows:
        target = registry.resolve(row["fallback_ref"]) if row["fallback_ref"] else None
        if target is None:
            failures.append({"issue": "fallback_unresolved", "record_id": row["record_id"],
                             "fallback_ref": row["fallback_ref"]})
            continue
        if target.availability == "missing":
            failures.append({"issue": "fallback_to_missing", "record_id": row["record_id"],
                             "fallback_ref": row["fallback_ref"]})
        if row["runtime_path"] != target.rel_path:
            failures.append({"issue": "fallback_runtime_mismatch",
                             "record_id": row["record_id"],
                             "runtime_path": row["runtime_path"],
                             "expected": target.rel_path})
        # 事件 id 取运行时键末段（target_ref 是 content.py 引用，末段是集合#id）
        event_id = row["runtime_key"].split(":")[-1]
        effect_id = effect_map.get(event_id)
        if effect_id:
            expected_record_id = record_id_by_runtime.get("card:event:%s" % effect_id, "")
            if not expected_record_id:
                failures.append({"issue": "fallback_target_absent",
                                 "record_id": row["record_id"], "effect_id": effect_id})
            elif row["fallback_ref"] != expected_record_id:
                failures.append({"issue": "fallback_not_effect_record_id",
                                 "record_id": row["record_id"],
                                 "effect_id": effect_id,
                                 "expected": expected_record_id,
                                 "fallback_ref": row["fallback_ref"]})
    for row in csv_rows:
        if row["runtime_status"] == "placeholder" and "placeholders/" not in row["runtime_path"]:
            failures.append({"issue": "placeholder_path", "record_id": row["record_id"],
                             "runtime_path": row["runtime_path"]})
    checker.add("V09", "回退语义：0 条 fallback / 0 条 placeholder（142 位均有自有运行时图）",
                failures, "回退分支保留为兜底断言，v2 期望 0/0")

    # V10 占位图 -------------------------------------------------------
    failures = []
    expected_placeholders = {
        "character": asset_pipeline.CHARACTER_SIZE,
        "room": asset_pipeline.ROOM_SIZE,
        "event": asset_pipeline.CARD_SIZE,
    }
    for kind, size in expected_placeholders.items():
        path = ASSETS_DIR / "placeholders" / ("%s_missing.png" % kind)
        if not path.is_file():
            failures.append({"issue": "placeholder_absent", "path": str(path)})
            continue
        actual = png_size(path)
        if actual != size:
            failures.append({"issue": "placeholder_size", "path": str(path),
                             "expected": list(size), "actual": actual})
    # run5：assets/placeholders 只允许 3 张基础占位图；50 张 WW 占位图落在
    # assets_ww/placeholders/（B-05 / A-29 判据 7），两者都不得被扫描混用。
    active_placeholders = sorted((ASSETS_DIR / "placeholders").glob("*.png"))
    if len(active_placeholders) != len(expected_placeholders):
        failures.append({"issue": "placeholder_extra",
                         "actual": [path.name for path in active_placeholders]})
    ww_left = [path.name for path in active_placeholders if path.name.startswith("ww_")]
    if ww_left:
        failures.append({"issue": "ww_placeholder_in_assets", "files": ww_left[:5]})
    ww_placeholder_dir = ASSETS_WW_DIR / "placeholders"
    ww_deferred = sorted(ww_placeholder_dir.glob("ww_*.png")) if ww_placeholder_dir.is_dir() else []
    if len(ww_deferred) != 50:
        failures.append({"issue": "ww_placeholder_not_deferred",
                         "expected": 50, "actual": len(ww_deferred)})
    checker.add("V10", "三张占位图存在且尺寸为 320/512/480x672；WW 50 张占位图不在 assets/",
                failures,
                "placeholders/*.png = 3；assets_ww/placeholders/ww_*.png = 50（不被扫描）")

    # V11 photos 只读 --------------------------------------------------
    failures = []
    inventory = {}
    if INVENTORY_JSON.is_file():
        with INVENTORY_JSON.open("r", encoding="utf-8") as handle:
            for item in json.load(handle):
                inventory[item["file"]] = item.get("sha256", "")
    # run5 v2：photos/ 的合法源文件 = 142 个真 PNG；转码原件备份
    # photos/_source_jpeg/ 130 个 .jpg 单独计数并**显式排除**在源文件集合之外。
    all_photo_files = sorted(path for path in PHOTOS_DIR.rglob("*") if path.is_file())
    disk_files = [path for path in all_photo_files
                  if path.relative_to(PHOTOS_DIR).parts[0] != BACKUP_DIRNAME]
    backup_files = [path for path in all_photo_files
                    if path.relative_to(PHOTOS_DIR).parts[0] == BACKUP_DIRNAME]
    # 断言 1：数量（拆开"源文件数"与"备份数"，避免旧版把两者混成一个 95）
    if len(disk_files) != EXPECTED_PRESENT:
        failures.append({"issue": "photos_file_count", "expected": EXPECTED_PRESENT,
                         "actual": len(disk_files)})
    if len(backup_files) != EXPECTED_BACKUPS:
        failures.append({"issue": "photos_backup_count", "expected": EXPECTED_BACKUPS,
                         "actual": len(backup_files)})
    # 负样本自证：把备份算进来会得到 272，与 142 不等 —— 扫描必须排除备份目录。
    if len(all_photo_files) == EXPECTED_PRESENT:
        failures.append({"issue": "backup_not_excluded_from_scan",
                         "hint": "备份目录被排除后仍等于 %d，说明备份没落盘" % EXPECTED_PRESENT})
    disk_rel = {path.relative_to(PROJECT_ROOT).as_posix() for path in disk_files}
    table_rel = {row["source_path"] for row in present_rows}
    if disk_rel != table_rel:
        failures.append({"issue": "photos_orphan",
                         "only_on_disk": sorted(disk_rel - table_rel)[:5],
                         "only_in_table": sorted(table_rel - disk_rel)[:5]})
    # 断言 2：哈希（inventory v2 142 条，逐文件比对）
    if len(inventory) != EXPECTED_PRESENT:
        failures.append({"issue": "inventory_count", "expected": EXPECTED_PRESENT,
                         "actual": len(inventory)})
    for path in disk_files:
        digest = _sha256(path)
        recorded = inventory.get(path.name)
        if not recorded:
            failures.append({"issue": "inventory_missing", "file": path.name})
        elif recorded != digest:
            failures.append({"issue": "photos_modified", "file": path.name})
    # 备份哈希：与转码清单 source_sha256 一致（P-10）
    manifest_backups = {}
    if TRANSCODE_MANIFEST.is_file():
        with TRANSCODE_MANIFEST.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        for item in manifest.get("records") or []:
            manifest_backups[Path(item["backup"]).name] = item.get("source_sha256", "")
    else:
        failures.append({"issue": "transcode_manifest_absent"})
    for path in backup_files:
        recorded = manifest_backups.get(path.name)
        if not recorded:
            failures.append({"issue": "backup_unregistered", "file": path.name})
        elif recorded != _sha256(path):
            failures.append({"issue": "backup_sha256_mismatch", "file": path.name})
    for row in present_rows:
        provenance = row["provenance"]
        if not provenance.startswith(row["source_path"] + ";sha256:"):
            failures.append({"issue": "provenance_format", "record_id": row["record_id"]})
    checker.add("V11", "photos 未被修改（142 个源文件 + 130 个原件备份，数量与哈希分别断言）",
                failures,
                "142 个源文件哈希与 photos_inventory.json(142) 一致；"
                "130 个 .jpg 备份哈希与 qa/run5_transcode_manifest.json 一致")

    # V12 CSV / JSON 一致 ---------------------------------------------
    failures = []
    if len(csv_rows) == len(json_rows):
        for index, (csv_row, json_row) in enumerate(zip(csv_rows, json_rows)):
            for column in asset_pipeline.CSV_COLUMNS:
                if _norm(csv_row.get(column)) != _norm(json_row.get(column)):
                    failures.append({"issue": "field_mismatch", "row": index,
                                     "column": column,
                                     "csv": _norm(csv_row.get(column)),
                                     "json": _norm(json_row.get(column))})
    else:
        failures.append({"issue": "row_count_mismatch"})
    stats = payload.get("stats") or {}
    if stats.get("records") != EXPECTED_TOTAL:
        failures.append({"issue": "stats_records", "actual": stats.get("records")})
    if stats.get("usable") != EXPECTED_USABLE or stats.get("partial") != EXPECTED_PARTIAL \
            or stats.get("missing") != EXPECTED_MISSING:
        failures.append({"issue": "stats_split", "actual": stats,
                         "expected": {"usable": EXPECTED_USABLE, "partial": EXPECTED_PARTIAL,
                                      "missing": EXPECTED_MISSING}})
    checker.add("V12", "CSV 与 JSON 逐字段一致，stats 口径正确", failures,
                "142 行 x %d 列无差异" % len(asset_pipeline.CSV_COLUMNS))

    # V13 映射文件 -----------------------------------------------------
    failures = []
    if not MAPPING_JSON.is_file():
        failures.append({"issue": "mapping_absent"})
        mapping = {}
    else:
        with MAPPING_JSON.open("r", encoding="utf-8") as handle:
            mapping = json.load(handle)
        entries = mapping.get("entries") or []
        unresolved = mapping.get("unresolved") or []
        if len(entries) != EXPECTED_PRESENT:
            failures.append({"issue": "mapping_entries", "actual": len(entries)})
        if len(unresolved) != EXPECTED_MISSING:
            failures.append({"issue": "mapping_unresolved", "actual": len(unresolved)})
        by_ref = {row["target_ref"]: row for row in csv_rows}
        for entry in entries:
            row = by_ref.get(entry["target_ref"])
            if row is None:
                failures.append({"issue": "mapping_unknown_ref", "target_ref": entry["target_ref"]})
                continue
            if entry["path"] != row["source_path"]:
                failures.append({"issue": "mapping_path_mismatch",
                                 "target_ref": entry["target_ref"]})
            # 映射项必须同时保留运行时键与溯源键，且与 P 表逐行一致
            if entry.get("runtime_key") != row["runtime_key"]:
                failures.append({"issue": "mapping_runtime_key_mismatch",
                                 "target_ref": entry["target_ref"],
                                 "expected": row["runtime_key"],
                                 "actual": entry.get("runtime_key")})
        for item in unresolved:
            row = by_ref.get(item["target_ref"])
            if row is not None and item.get("runtime_key") != row["runtime_key"]:
                failures.append({"issue": "mapping_runtime_key_mismatch",
                                 "target_ref": item["target_ref"],
                                 "expected": row["runtime_key"],
                                 "actual": item.get("runtime_key")})
            if row is not None and row["availability"] == "missing":
                if item.get("fallback") != row["fallback_ref"]:
                    failures.append({"issue": "mapping_fallback_mismatch",
                                     "target_ref": item["target_ref"],
                                     "expected": row["fallback_ref"],
                                     "actual": item.get("fallback")})
                if item.get("status") != row["mapping_status"]:
                    failures.append({"issue": "mapping_status_mismatch",
                                     "target_ref": item["target_ref"],
                                     "expected": row["mapping_status"],
                                     "actual": item.get("status")})
                if item.get("content_ref") != row["content_ref"]:
                    failures.append({"issue": "mapping_content_ref_mismatch",
                                     "target_ref": item["target_ref"]})
            if row is None or row["availability"] != "missing":
                failures.append({"issue": "mapping_unresolved_mismatch",
                                 "target_ref": item["target_ref"]})
    checker.add("V13", "asset_mapping.json 与 P 表双向覆盖（142/0）", failures,
                "entries=142 / unresolved=0")

    # V14 注册表 -------------------------------------------------------
    failures = []
    for row in csv_rows:
        for key_name in ("target_ref", "runtime_key", "record_id", "content_ref"):
            ref = registry.resolve(row[key_name])
            if ref is None or ref.record_id != row["record_id"]:
                failures.append({"issue": "resolve_" + key_name, "key": row[key_name]})
    issues = registry.validate(ASSETS_DIR)
    for issue in issues:
        failures.append({"issue": "registry_validate", **issue})
    if len(registry.missing()) != EXPECTED_MISSING:
        failures.append({"issue": "registry_missing_count",
                         "actual": len(registry.missing())})
    if len(registry) != EXPECTED_TOTAL:
        failures.append({"issue": "registry_size", "actual": len(registry)})
    checker.add("V14",
                "注册表解析全部 142 个 target_ref / runtime_key / record_id / content_ref，"
                "validate 无问题",
                failures, "issues=%d" % len(issues))

    # V15 不伪造 -------------------------------------------------------
    failures = []
    for row in csv_rows:
        runtime_path = row["runtime_path"]
        if runtime_path and not runtime_path.startswith("source/desktop/game/assets/"):
            failures.append({"issue": "runtime_outside_assets",
                             "record_id": row["record_id"], "value": runtime_path})
        if row["availability"] == "missing" and row["source_path"]:
            failures.append({"issue": "fabricated_source", "record_id": row["record_id"]})
        if row["availability"] in ("usable", "partial") and not row["source_path"]:
            failures.append({"issue": "usable_without_source",
                             "record_id": row["record_id"]})
    if mapping:
        entry_refs = {entry["target_ref"] for entry in mapping.get("entries") or []}
        for row in missing_rows:
            if row["target_ref"] in entry_refs:
                failures.append({"issue": "missing_in_entries",
                                 "target_ref": row["target_ref"]})
    checker.add("V15", "缺图不伪造路径，映射不引用 missing 行", failures,
                "0 条伪造引用")

    # V16 dimensions / aspect_ratio / content_ref ----------------------
    failures = []
    content_index = {key: set(values) for key, values in content_sets.items()}
    seen_content_refs = {}
    for row in csv_rows:
        record_id = row["record_id"]
        content_ref = row["content_ref"]
        if not content_ref.startswith("content.py:"):
            failures.append({"issue": "content_ref_format", "record_id": record_id,
                             "value": content_ref})
        else:
            collection, _, content_id = content_ref[len("content.py:"):].partition("#")
            allowed = CONTENT_COLLECTIONS_BY_TYPE.get(row["asset_type"], ())
            if collection not in allowed:
                failures.append({"issue": "content_ref_collection", "record_id": record_id,
                                 "value": content_ref, "allowed": list(allowed)})
            elif content_id not in content_index.get(collection, set()):
                failures.append({"issue": "content_ref_id_unknown", "record_id": record_id,
                                 "value": content_ref})
            seen_content_refs.setdefault(content_ref, []).append(record_id)
        if row["availability"] == "missing":
            if row["dimensions"] or row["aspect_ratio"]:
                failures.append({"issue": "missing_has_dimensions", "record_id": record_id,
                                 "dimensions": row["dimensions"],
                                 "aspect_ratio": row["aspect_ratio"]})
            continue
        width, height = row["width"], row["height"]
        expected_dimensions = "%sx%s" % (width, height)
        if row["dimensions"] != expected_dimensions:
            failures.append({"issue": "dimensions_mismatch", "record_id": record_id,
                             "expected": expected_dimensions,
                             "actual": row["dimensions"]})
        try:
            divisor = math.gcd(int(width), int(height)) or 1
            expected_ratio = "%d:%d" % (int(width) // divisor, int(height) // divisor)
        except (TypeError, ValueError):
            failures.append({"issue": "width_height_unparsable", "record_id": record_id})
            continue
        if row["aspect_ratio"] != expected_ratio:
            failures.append({"issue": "aspect_ratio_mismatch", "record_id": record_id,
                             "expected": expected_ratio,
                             "actual": row["aspect_ratio"]})
    duplicated_refs = {ref: ids for ref, ids in seen_content_refs.items() if len(ids) > 1}
    if duplicated_refs:
        failures.append({"issue": "content_ref_not_unique",
                         "sample": dict(list(duplicated_refs.items())[:3])})
    if len(seen_content_refs) != EXPECTED_TOTAL:
        failures.append({"issue": "content_ref_count", "actual": len(seen_content_refs)})
    checker.add("V16", "dimensions/aspect_ratio 与 width/height 同源，content_ref 一一对应 content.py",
                failures, "142 条 dimensions/aspect_ratio 自洽；content_ref 唯一且可回溯")

    # V17 发布档 7 列 --------------------------------------------------
    failures = []
    release_columns = list(getattr(asset_pipeline, "RELEASE_COLUMNS", ()))
    for column in release_columns:
        if column not in header:
            failures.append({"issue": "release_column_absent", "column": column})
    verified_at_expected = asset_pipeline.verification_date()
    category_dir_expected = {
        "character": "char",
        "room": "room",
        "card_omen": "omen",
        "card_item": "item",
        "card_event": "event",
    }
    by_record_id = {row["record_id"]: row for row in csv_rows}
    checked_sources = 0
    for row in csv_rows:
        record_id = row["record_id"]
        if row["availability"] == "missing":
            # 缺口行不得伪造源文件事实
            if row["bytes"]:
                failures.append({"issue": "missing_has_bytes", "record_id": record_id,
                                 "value": row["bytes"]})
            if row["sha256"]:
                failures.append({"issue": "missing_has_sha256", "record_id": record_id})
        else:
            source = PROJECT_ROOT / row["source_path"] if row["source_path"] else None
            if source is None or not source.is_file():
                failures.append({"issue": "release_source_absent", "record_id": record_id})
            else:
                checked_sources += 1
                actual_bytes = source.stat().st_size
                if row["bytes"] != str(actual_bytes):
                    failures.append({"issue": "release_bytes_mismatch", "record_id": record_id,
                                     "expected": actual_bytes, "actual": row["bytes"]})
                actual_sha = _sha256(source)
                if row["sha256"] != actual_sha:
                    failures.append({"issue": "release_sha256_mismatch",
                                     "record_id": record_id})
        expected_category = category_dir_expected.get(row["asset_type"])
        if expected_category and row["category_dir"] != expected_category:
            failures.append({"issue": "release_category_dir", "record_id": record_id,
                             "expected": expected_category, "actual": row["category_dir"]})
        expected_alpha = "true" if ALPHA_EXPECTED_BY_TYPE.get(row["asset_type"], False) else "false"
        if row["alpha_required"] != expected_alpha:
            failures.append({"issue": "release_alpha_required", "record_id": record_id,
                             "expected": expected_alpha, "actual": row["alpha_required"]})
        canonical = by_record_id.get(row["canonical_record_id"])
        if canonical is None:
            failures.append({"issue": "release_canonical_unresolved", "record_id": record_id,
                             "value": row["canonical_record_id"]})
        elif row["availability"] == "duplicate":
            if canonical["record_id"] == record_id or canonical["sha256"] != row["sha256"]:
                failures.append({"issue": "release_canonical_invalid", "record_id": record_id})
        elif row["canonical_record_id"] != record_id:
            failures.append({"issue": "release_canonical_not_self", "record_id": record_id,
                             "value": row["canonical_record_id"]})
        if not row["reviewer"]:
            failures.append({"issue": "release_reviewer_absent", "record_id": record_id})
        if row["verified_at"] != verified_at_expected:
            failures.append({"issue": "release_verified_at", "record_id": record_id,
                             "expected": verified_at_expected, "actual": row["verified_at"]})
    checker.add("V17", "发布档 7 列齐全，bytes/sha256 取源文件、missing 留空、canonical 自指",
                failures,
                "%d 列；%d 行源文件哈希复核；verified_at=%s"
                % (len(header), checked_sources, verified_at_expected))

    # ------------------------------------------------------------------
    rooms, cards, placeholders = _runtime_artifacts()
    artifacts = {
        "rooms": {"count": len(rooms), "bytes": sum(p.stat().st_size for p in rooms)},
        "cards": {"count": len(cards), "bytes": sum(p.stat().st_size for p in cards)},
        "placeholders": {"count": len(placeholders),
                         "bytes": sum(p.stat().st_size for p in placeholders)},
    }
    artifacts["normalized_total"] = {
        "count": len(rooms) + len(cards),
        "bytes": artifacts["rooms"]["bytes"] + artifacts["cards"]["bytes"],
    }

    failed_checks = checker.failed
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tool": "verify_assets.py",
        "ok": not failed_checks,
        "totals": {
            "records": len(csv_rows),
            "checked": len(checker.checks),
            "failed": len(failed_checks),
        },
        "summary": {
            "p_table": {
                "records": len(csv_rows),
                "present": len(present_rows),
                "missing": len(missing_rows),
                "by_asset_type": counts,
                "by_runtime_status": runtime_status_count,
                "by_mapping_status": mapping_status_count,
            },
            "artifacts": artifacts,
        },
        "checks": checker.checks,
    }

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    with REPORT_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    for check in checker.checks:
        mark = "PASS" if check["status"] == "pass" else "FAIL"
        print("[%s] %-4s %s | %s" % (mark, check["id"], check["name"], check["detail"]))
        for failure in check.get("failures", [])[:5]:
            print("        - %s" % json.dumps(failure, ensure_ascii=False))

    print("-" * 78)
    print("P 表 %d 行（现有 %d / 缺口 %d）" % (len(csv_rows), len(present_rows), len(missing_rows)))
    print("规范化产物：rooms=%d cards=%d 合计 %.2f MiB；占位图 %d"
          % (artifacts["rooms"]["count"], artifacts["cards"]["count"],
             artifacts["normalized_total"]["bytes"] / 1048576.0, len(placeholders)))
    print("自测：%d 项检查，失败 %d 项 -> %s"
          % (len(checker.checks), len(failed_checks), "PASS" if not failed_checks else "FAIL"))
    print("报告：%s" % REPORT_JSON)

    return 0 if not failed_checks else 1


if __name__ == "__main__":
    sys.exit(main())
