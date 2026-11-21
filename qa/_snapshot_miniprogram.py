#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 source/miniprogram 零变更快照（run5 S0，供 A-29 判据 9 比对）。

一次性工具：本轮任务只改桌面端，小程序端全树应保持不变。没有 git 可用，
因此用"文件清单 + 逐文件 sha256 + 聚合树哈希"作为基线，A-29 运行时重算比对。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GAME_DIR.parents[2]
TARGET = PROJECT_ROOT / "source" / "miniprogram"
OUT = GAME_DIR / "qa" / "run5_miniprogram_snapshot.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    files = sorted(path for path in TARGET.rglob("*") if path.is_file())
    entries = []
    for path in files:
        entries.append({
            "path": path.relative_to(PROJECT_ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    aggregate = hashlib.sha256(
        "\n".join("%s:%s" % (item["path"], item["sha256"]) for item in entries).encode("utf-8")
    ).hexdigest()
    mtimes = [os.path.getmtime(path) for path in files]
    document = {
        "schema": "run5_miniprogram_snapshot/v1",
        "captured_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "note": "run5 S0 基线：本轮只改桌面端 P 表与资源，未触碰 source/miniprogram。",
        "tree": "source/miniprogram",
        "files": len(entries),
        "tree_sha256": aggregate,
        "newest_mtime": (datetime.fromtimestamp(max(mtimes)).strftime("%Y-%m-%dT%H:%M:%S")
                         if mtimes else ""),
        "entries": entries,
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("files=%d tree_sha256=%s newest_mtime=%s" %
          (len(entries), aggregate, document["newest_mtime"]))
    print("-> %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
