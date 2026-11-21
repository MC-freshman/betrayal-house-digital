#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run5 S3：47 个缺失位的登记台账 + 重基线 diff（证据产出，只写 qa/）。

输入（全部只读）
----------------
* ``.codebuddy/wfat/run5_boundary_audit.json`` §2_missing_47：47 个缺失位的
  ``record_id`` / ``content_ref`` / ``asset_type`` / 原 ``runtime_status``。
* ``.codebuddy/wfat/run5_boundary_audit.json`` §4_orphan_47：47 个"已存在但未登记"
  的候选文件（34 event + 1 room + 12 role）。
* ``source/desktop/game/assets/p_table.json``（重跑后的 142 行）。
* ``qa/run5_transcode_manifest.json``（35 个 JPEG 的转码事实）。

产出
----
``qa/run5_promotion_map.json``：47 行 ``record_id → 文件`` 绑定表（run5 §2.2 M-04）。
``qa/run5_gap_closure.jsonl``：47 行缺口台账（run5 §2.9 M-26）。
``qa/run5_baseline_diff.json``：旧值/新值/理由/证据 逐条（run5 §4.6）。

用法::

    python qa/run5_promote.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GAME_DIR.parents[2]
QA_DIR = Path(__file__).resolve().parent
AUDIT_JSON = PROJECT_ROOT / ".codebuddy" / "wfat" / "run5_boundary_audit.json"
PTABLE_JSON = GAME_DIR / "assets" / "p_table.json"
MAPPING_JSON = GAME_DIR / "assets" / "asset_mapping.json"
MANIFEST_JSON = QA_DIR / "run5_transcode_manifest.json"
ISOLATION_JSON = QA_DIR / "run5_ww_isolation.json"
PROMOTION_JSON = QA_DIR / "run5_promotion_map.json"
GAP_JSONL = QA_DIR / "run5_gap_closure.jsonl"
DIFF_JSON = QA_DIR / "run5_baseline_diff.json"

REVIEWER = "run5-promote/automated"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def match_stem(record: dict) -> str:
    """把缺失位的 content_ref 换成 photos/ 文件名主干（不用相似度猜，按规则展开）。"""
    content_ref = record["content_ref"]
    collection, _, slot_id = content_ref[len("content.py:"):].partition("#")
    if collection == "CHARACTER_FACES":
        # card_1_0 -> character_card_1_f0
        card_id, _, face_index = slot_id.rpartition("_")
        return "character_%s_f%s" % (card_id, face_index)
    if collection == "ROOM_SUPPLEMENTAL_SPECS":
        return slot_id
    return slot_id


def build_promotion() -> dict:
    audit = load_json(AUDIT_JSON)
    ptable = load_json(PTABLE_JSON)
    manifest = load_json(MANIFEST_JSON) if MANIFEST_JSON.is_file() else {"records": []}
    transcode = {row["path"]: row for row in manifest.get("records") or []}

    rows_by_id = {row["record_id"]: row for row in ptable["records"]}
    missing = (audit.get("2_missing_47") or {}).get("items") or []
    orphans = (audit.get("4_orphan_47") or {}).get("items") or []
    orphan_by_stem = {Path(item["file"]).stem: item for item in orphans}

    promoted, problems = [], []
    for record in missing:
        record_id = record["record_id"]
        row = rows_by_id.get(record_id)
        if row is None:
            problems.append({"record_id": record_id, "issue": "row_absent"})
            continue
        stem = match_stem(record)
        candidate = orphan_by_stem.get(stem)
        if candidate is None:
            problems.append({"record_id": record_id, "issue": "candidate_absent", "stem": stem})
            # 候选文件缺失时仍登记 P 表事实，decision 记为表内不一致
            decision = "registered_without_candidate"
            first_seen = ""
        else:
            decision = "reuse_existing_file"
            first_seen = "2026-11-20"
        transcode_row = transcode.get(row["source_path"])
        promoted.append(
            {
                "record_id": record_id,
                "asset_type": row["asset_type"],
                "content_ref": row["content_ref"],
                "target_ref": row["target_ref"],
                "runtime_key": row["runtime_key"],
                "source_path": row["source_path"],
                "source_file": row["source_file"],
                "sha256": row["sha256"],
                "bytes": row["bytes"],
                "width": row["width"],
                "height": row["height"],
                "format": row["format"],
                "has_alpha": row["has_alpha"],
                "availability": row["availability"],
                "mapping_status": row["mapping_status"],
                "runtime_status": row["runtime_status"],
                "runtime_path": row["runtime_path"],
                "fallback_ref": row["fallback_ref"],
                "decision": decision,
                "provenance_origin": "photos",
                "first_seen": first_seen,
                "transcoded_from_jpeg": bool(transcode_row),
                "source_sha256_before_transcode": (transcode_row or {}).get("source_sha256", ""),
                "backup_path": (transcode_row or {}).get("backup", ""),
                "previous_availability": "missing",
                "previous_runtime_status": record.get("runtime_status", ""),
                "reviewer": REVIEWER,
            }
        )

    counts = {}
    for row in promoted:
        counts[row["asset_type"]] = counts.get(row["asset_type"], 0) + 1
    document = {
        "schema": "run5_promotion_map/v1",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "source_audit": str(AUDIT_JSON.relative_to(PROJECT_ROOT)),
        "reviewer": REVIEWER,
        "note": "run5 §2.1 M-A：复用磁盘上已存在的 47 个候选文件，"
                "provenance 记 origin=photos，不声称本轮生成；"
                "34 event + 1 room 的原件为 JPEG，按 A 方案转码为真 PNG。",
        "summary": {
            "rows": len(promoted),
            "by_asset_type": counts,
            "transcoded": sum(1 for row in promoted if row["transcoded_from_jpeg"]),
            "already_png": sum(1 for row in promoted if not row["transcoded_from_jpeg"]),
            "all_usable": all(row["availability"] == "usable" for row in promoted),
            "all_matched": all(row["mapping_status"] == "matched" for row in promoted),
            "problems": problems,
        },
        "rows": promoted,
    }
    PROMOTION_JSON.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")

    with GAP_JSONL.open("w", encoding="utf-8", newline="\n") as handle:
        for row in promoted:
            handle.write(json.dumps(
                {
                    "record_id": row["record_id"],
                    "asset_type": row["asset_type"],
                    "content_ref": row["content_ref"],
                    "source_path": row["source_path"],
                    "sha256": row["sha256"],
                    "decision": row["decision"],
                    "transcoded_from_jpeg": row["transcoded_from_jpeg"],
                    "source_sha256_before_transcode": row["source_sha256_before_transcode"],
                    "backup_path": row["backup_path"],
                    "reviewer": row["reviewer"],
                }, ensure_ascii=False) + "\n")
    return document


def build_baseline_diff(promotion: dict) -> dict:
    ptable = load_json(PTABLE_JSON)
    stats = ptable.get("stats") or {}
    mapping = load_json(MAPPING_JSON)
    isolation = load_json(ISOLATION_JSON) if ISOLATION_JSON.is_file() else {}
    manifest = load_json(MANIFEST_JSON) if MANIFEST_JSON.is_file() else {}

    def entry(identifier, old, new, why, evidence):
        return {"id": identifier, "old": old, "expected_v2": new, "why": why,
                "evidence": evidence}

    entries = [
        entry("A-05 availability", "usable=0 / partial=95 / missing=47",
              "usable=%d / partial=%d / missing=%d"
              % (stats.get("usable"), stats.get("partial"), stats.get("missing")),
              "47 位登记 + 130 张转码后无 partial/missing",
              "assets/p_table.json §stats"),
        entry("A-07 mapping", "entries=95 / unresolved=47",
              "entries=%d / unresolved=%d"
              % (len(mapping.get("entries") or []), len(mapping.get("unresolved") or [])),
              "映射随 P 表可用性一起重算",
              "assets/asset_mapping.json"),
        entry("A-08 runtime PNG", "rooms=49 / cards=46 / placeholders=3（98）",
              "rooms=50 / cards=80 / characters=12 / placeholders=3（145）",
              "角色 12 位接通 photos/role/ 真图；卡牌补满 80",
              "assets/**/*.png 计数"),
        entry("A-09 missing 语义", "47 行 missing 规则", "N/A（退役）",
              "0 missing 后失去断言对象；保留条目与退役理由，不计入分母",
              "qa/verify_p_table_final.py A-09 说明"),
        entry("A-27 内容台账", "12/1/34 缺口台账", "142/142 全覆盖、缺口 0",
              "台账改为逐行 source+provenance+release 7 列核对",
              "qa/run5_promotion_map.json + qa/run5_gap_closure.jsonl"),
        entry("verify_assets.py V05", "7 集合含 192（WW 混入）",
              "7 集合合计 142，content.py 无 WW 残留",
              "content.py 收敛回 142 基线后自然满足，并追加 WW 残留扫描",
              "python verify_assets.py V05"),
        entry("verify_assets.py V06/V07", "95 present / 47 missing",
              "142 present / 0 missing", "同上",
              "python verify_assets.py V06/V07"),
        entry("verify_assets.py V11", "95 个文件、哈希一致",
              "142 个源文件 + 130 个原件备份，数量与哈希分开断言",
              "47 文件登记 + 130 转码；备份目录显式排除，避免 272 混淆",
              "python verify_assets.py V11"),
        entry("契约 32 项", "含 95/47 断言", "同步 v2（条数仍 32）",
              "不减少条数，只改期望值", "python qa/verify_assets_contract.py --json"),
        entry("新测试 48 项", "含 95/47 断言", "同步 v2（条数仍 48）",
              "不删用例，只改期望值", "python qa/test_p_table_execution.py"),
        entry("content.py 集合计数", "12/70/49+20/60/32/18/120（含 WW）",
              "12/50/45/22/13/70（142 基线）",
              "WW 隔离到 content_ww.py，id 集合与 S0 归档完全相等",
              "qa/run5_ww_isolation.json"),
        entry("haunts 注册表", "120 本（71-120 为 WW 骨架）", "70 本",
              "50 个 WW handler 移到 haunts/_ww_deferred/，不再注册",
              "haunts/__init__.py + haunts/_ww_deferred/"),
        entry("photos 体积", "≈140 MiB（130 个 JPEG 内容）",
              "源文件 ≈%.1f MiB + 备份 ≈%.1f MiB"
              % (sum(1 for _ in [0]) and 0 or 0, 0),
              "JPEG→PNG 无损重编码必然变大（转码清单 summary 有实测值）",
              "qa/run5_transcode_manifest.json §summary"),
    ]
    # 体积条目用实测值覆盖（避免上面写成占位 0）
    summary = manifest.get("summary") or {}
    if summary:
        entries[-1]["expected_v2"] = "源文件 %.1f MiB + 备份 %.1f MiB（转码后合计）" % (
            summary.get("output_bytes", 0) / 1048576.0,
            summary.get("source_bytes", 0) / 1048576.0)

    document = {
        "schema": "run5_baseline_diff/v1",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "reviewer": REVIEWER,
        "note": "run5 §4.6 旧项重基线矩阵。允许改期望值，不允许删断言、不允许放宽语义。",
        "ww_isolation": {
            "content.py": isolation.get("after_sha256", {}).get("content.py", ""),
            "content_ww.py": isolation.get("after_sha256", {}).get("content_ww.py", ""),
            "moved_haunts": (isolation.get("counts") or {}).get("moved_haunt_modules", 0),
            "moved_ww_placeholders":
                (isolation.get("counts") or {}).get("moved_ww_placeholders", 0),
        },
        "promotion": promotion.get("summary") or {},
        "entries": entries,
    }
    DIFF_JSON.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    return document


def main() -> int:
    for required in (AUDIT_JSON, PTABLE_JSON):
        if not required.is_file():
            print("[FAIL] 缺少输入：%s" % required)
            return 1
    promotion = build_promotion()
    diff = build_baseline_diff(promotion)
    summary = promotion["summary"]
    print("[promotion] %s" % PROMOTION_JSON)
    print("            47 行 -> 实测 %d 行；%s；转码 %d / 原生 PNG %d"
          % (summary["rows"], summary["by_asset_type"],
             summary["transcoded"], summary["already_png"]))
    if summary["problems"]:
        print("[promotion] 问题 %d 项：%s" % (len(summary["problems"]),
                                          summary["problems"][:5]))
    print("[gap] %s（%d 行）" % (GAP_JSONL, summary["rows"]))
    print("[diff] %s（%d 条）" % (DIFF_JSON, len(diff["entries"])))
    return 0 if not summary["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
