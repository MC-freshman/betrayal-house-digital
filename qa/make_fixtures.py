#!/usr/bin/env python
"""生成 qa/fixtures/ 下的负样本（确定性、可重复、不依赖网络与 Pillow）。

覆盖 6 类必测负样本 + 2 个辅助样本：
    zero_byte.png                 0 字节文件
    corrupt.png                   PNG 魔数正确、IHDR 截断
    bad.json                      非法 JSON
    duplicate_record_id.json      record_id 重复
    path_traversal.json           含 ../ 的键与越界运行时路径
    bom.json                      UTF-8 BOM 开头的合法清单
    mapping_without_records.json  映射文件（无 records 且无同目录 P 表）
    outside/evil.png             assets 目录外的真实 PNG（用于越界检查）

用法::

    python qa/make_fixtures.py      # 幂等覆盖，不改动 assets/ 与 photos/

说明：fixtures 只服务测试，不得进入发布产物；本脚本不读取也不写入 assets/。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# 1x1 RGB+alpha PNG（固定字节，避免依赖 Pillow 生成导致各机不一致）
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

ROOM_PLACEHOLDER = "source/desktop/game/assets/placeholders/room_missing.png"
EVENT_PLACEHOLDER = "source/desktop/game/assets/placeholders/event_missing.png"


def _record(record_id, target_ref, asset_type, runtime_path, availability="partial",
            runtime_status="ok", **extra):
    row = {
        "record_id": record_id,
        "source_file": "",
        "source_path": "",
        "asset_type": asset_type,
        "width": None,
        "height": None,
        "dimensions": "",
        "aspect_ratio": "",
        "format": "unknown",
        "has_alpha": False,
        "decodable": "not_checked",
        "semantic_hint": "",
        "match_candidate": "",
        "usable_fields": [],
        "availability": availability,
        "mapping_status": "matched",
        "target_ref": target_ref,
        "missing_note": "",
        "provenance": "",
        "runtime_path": runtime_path,
        "runtime_format": "png",
        "runtime_status": runtime_status,
        "fallback_ref": "",
        "quality_flags": [],
        "content_ref": "content.py:FIXTURES#%s" % record_id,
        "bytes": None,
        "sha256": "",
        "category_dir": "room" if asset_type == "room" else "event",
        "alpha_required": False,
        "canonical_record_id": record_id,
        "reviewer": "automated",
        "verified_at": "2026-11-19",
    }
    row.update(extra)
    return row


def _manifest(records):
    return {
        "schema_version": "1.2.0",
        "generated_at": "2026-11-19",
        "base_dir": "Betrayal at House on the Hill",
        "runtime_specs": {
            "room": {"width": 512, "height": 512, "format": "png"},
            "card": {"width": 480, "height": 672, "format": "png"},
            "character": {"width": 320, "height": 320, "format": "png"},
        },
        "stats": {"records": len(records)},
        "content_refs": {},
        "records": records,
    }


def _write_json(path: Path, payload, bom: bool = False) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def build() -> list:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    outside = FIXTURES / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    written = []

    # 1) 0 字节
    path = FIXTURES / "zero_byte.png"
    path.write_bytes(b"")
    written.append(path)

    # 2) 损坏 PNG：魔数与 IHDR 标记正确，但长度字段被截断（读头即失败）
    path = FIXTURES / "corrupt.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + b"\x00\x00")
    written.append(path)

    # 3) 非法 JSON
    path = FIXTURES / "bad.json"
    path.write_text('{"records": [ {"record_id": "P-ROOM-001", ', encoding="utf-8")
    written.append(path)

    # 4) record_id 重复
    path = FIXTURES / "duplicate_record_id.json"
    _write_json(path, _manifest([
        _record("P-ROOM-001", "room:dup_a", "room", ROOM_PLACEHOLDER),
        _record("P-ROOM-001", "room:dup_b", "room", ROOM_PLACEHOLDER),
    ]))
    written.append(path)

    # 5) 路径穿越：键含 ../、运行时路径越出 assets 根
    path = FIXTURES / "path_traversal.json"
    _write_json(path, _manifest([
        _record("P-ROOM-998", "room:../escape", "room",
                "source/desktop/game/qa/fixtures/outside/evil.png"),
        _record("P-ROOM-997", "room:traversal_control", "room", ROOM_PLACEHOLDER),
        _record("P-ROOM-996", "room:traversal_missing", "room", "../outside/evil.png"),
    ]))
    written.append(path)

    # 6) BOM 开头的合法清单
    path = FIXTURES / "bom.json"
    _write_json(path, _manifest([
        _record("P-ROOM-001", "room:bom_room", "room", ROOM_PLACEHOLDER),
        _record("P-EVT-001", "card:event:bom_event", "card_event", EVENT_PLACEHOLDER),
    ]), bom=True)
    written.append(path)

    # 7) 映射文件：无 records，且故意不带同目录 p_table.json
    path = FIXTURES / "mapping_without_records.json"
    _write_json(path, {
        "version": "1.1.0",
        "generated_from": {"p_table": "(deleted)"},
        "entries": [],
        "unresolved": [],
    })
    written.append(path)

    # 8) assets 目录外的真实 PNG（越界检查用；不是 mimetype 陷阱）
    path = outside / "evil.png"
    path.write_bytes(TINY_PNG)
    written.append(path)

    return written


def main() -> int:
    for path in build():
        print("fixture: %s (%d B)" % (path.relative_to(FIXTURES.parent), path.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
