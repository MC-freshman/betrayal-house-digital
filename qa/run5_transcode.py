#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run5 S2：photos/ 的 130 个 JPEG 无损转码为真 PNG（像素等价）+ 原件备份。

判据（.codebuddy/wfat/run5_acceptance_criteria.md §3.4/§3.5）
------------------------------------------------------------
* P-01 解码：Pillow 打开 → ``convert("RGB")``（角色 12 张已是真 PNG，不参与）。
* P-02 不缩放 / 不裁剪 / 不旋转 / 不锐化：输出尺寸 == 源解码尺寸。
* P-03 编码：``save(format="PNG", optimize=True)``；不量化、不调色板化。
* P-04 像素等价：逐点比较 **max diff = 0 且 MAD = 0**，不满足即 FAIL。
* P-05 元数据：AIGC 标记不写入 PNG；事实通过清单的 ``source_sha256`` 保留。
* P-06 命名：文件名主干不变，扩展名仍是 ``.png``（不做 source_path 迁移）。
* P-09 备份：``photos/_source_jpeg/<category>/<stem>.jpg``（扩展名随真实格式）。
* P-10 备份 sha256 与清单 ``source_sha256`` 一致。

产出
----
``qa/run5_transcode_manifest.json``：130 条逐文件记录 + 汇总（Pillow 版本、
编码参数、耗时、操作者、像素等价结果）。
``photos/_source_jpeg/``：130 个 ``.jpg`` 原件。
``photos/<cat>/*.png``：原地替换为真 PNG（同名）。
``.codebuddy/wfat/photos_inventory.json``：142 条（转码后事实，A-31 判据 6）。

用法::

    python qa/run5_transcode.py --dry-run
    python qa/run5_transcode.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import PIL
from PIL import Image

GAME_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GAME_DIR.parents[2]
PHOTOS_DIR = PROJECT_ROOT / "photos"
BACKUP_DIR = PHOTOS_DIR / "_source_jpeg"
MANIFEST_JSON = GAME_DIR / "qa" / "run5_transcode_manifest.json"
INVENTORY_JSON = PROJECT_ROOT / ".codebuddy" / "wfat" / "photos_inventory.json"

CATEGORY_ORDER = ("role", "room", "event", "item", "omen")
CONTENT_HINT = {
    "role": "角色立绘",
    "room": "房间版块",
    "event": "卡牌·事件",
    "item": "卡牌·物品",
    "omen": "卡牌·预兆",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
OPERATOR = "run5-transcode/automated"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def magic(path: Path) -> str:
    head = path.open("rb").read(8)
    if head.startswith(PNG_SIGNATURE):
        return "png"
    if head.startswith(JPEG_SIGNATURE):
        return "jpeg"
    return "unknown"


def pixel_equal(left: Path, right: Path) -> dict:
    """逐点比较解码后的像素（P-04）。返回 max diff / MAD / 尺寸。"""
    with Image.open(left) as img:
        img.load()
        left_rgb = img.convert("RGB")
        left_size = img.size
        left_bytes = left_rgb.tobytes()
    with Image.open(right) as img:
        img.load()
        right_rgb = img.convert("RGB")
        right_size = img.size
        right_bytes = right_rgb.tobytes()

    if left_bytes == right_bytes:
        return {
            "max_diff": 0,
            "mad": 0.0,
            "pixels": len(left_bytes),
            "equal": True,
            "size_left": list(left_size),
            "size_right": list(right_size),
        }

    max_diff = 0
    total = 0
    for a, b in zip(left_bytes, right_bytes):
        diff = a - b if a >= b else b - a
        if diff > max_diff:
            max_diff = diff
        total += diff
    return {
        "max_diff": max_diff,
        "mad": total / float(len(left_bytes) or 1),
        "pixels": len(left_bytes),
        "equal": max_diff == 0,
        "size_left": list(left_size),
        "size_right": list(right_size),
    }


def transcode_one(src: Path, category: str, dry_run: bool) -> dict:
    source_sha = sha256_file(src)
    source_bytes = src.stat().st_size
    with Image.open(src) as img:
        img.load()
        source_size = img.size
        source_mode = img.mode
        source_format = img.format or "jpeg"
        converted = img.convert("RGB")

    backup = BACKUP_DIR / category / ("%s.jpg" % src.stem)
    target = src  # 原地替换，主干与扩展名不变（P-06）

    if dry_run:
        return {
            "path": src.relative_to(PROJECT_ROOT).as_posix(),
            "category": category,
            "would_transcode": True,
            "source_sha256": source_sha,
            "source_bytes": source_bytes,
            "size": list(source_size),
            "backup": backup.relative_to(PROJECT_ROOT).as_posix(),
        }

    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.is_file():
        if sha256_file(backup) != source_sha:
            raise SystemExit("备份已存在但 sha256 不同，拒绝覆盖：%s" % backup)
    else:
        shutil.copy2(src, backup)
    if sha256_file(backup) != source_sha:
        raise SystemExit("备份 sha256 与原件不一致：%s" % backup)

    started = time.time()
    converted.save(target, format="PNG", optimize=True)
    elapsed = time.time() - started

    if magic(target) != "png":
        raise SystemExit("转码后魔数不是 PNG：%s" % target)
    diff = pixel_equal(backup, target)
    if not diff["equal"] or diff["size_left"] != diff["size_right"]:
        raise SystemExit("像素等价校验失败（P-04）：%s %r" % (target, diff))

    target_sha = sha256_file(target)
    return {
        "path": target.relative_to(PROJECT_ROOT).as_posix(),
        "category": category,
        "backup": backup.relative_to(PROJECT_ROOT).as_posix(),
        "source_sha256": source_sha,
        "source_bytes": source_bytes,
        "source_format": source_format,
        "source_mode": source_mode,
        "sha256": target_sha,
        "bytes": target.stat().st_size,
        "width": source_size[0],
        "height": source_size[1],
        "dimensions": "%dx%d" % source_size,
        "pixel_equality": diff,
        "encode_seconds": round(elapsed, 3),
    }


def scan() -> dict:
    """枚举 photos/<cat>/*（排除 _source_jpeg 与子目录），按魔数分类。"""
    jpeg, png, other = [], [], []
    for category in CATEGORY_ORDER:
        base = PHOTOS_DIR / category
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if not path.is_file():
                continue
            kind = magic(path)
            entry = (category, path)
            if kind == "jpeg":
                jpeg.append(entry)
            elif kind == "png":
                png.append(entry)
            else:
                other.append(entry)
    return {"jpeg": jpeg, "png": png, "other": other}


def write_inventory() -> dict:
    """photos_inventory.json v2：142 条转码后事实（A-31 判据 6）。"""
    entries = []
    for category in CATEGORY_ORDER:
        base = PHOTOS_DIR / category
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if not path.is_file():
                continue
            with Image.open(path) as img:
                img.load()
                width, height = img.size
                mode = img.mode
                fmt = img.format or ""
                bands = img.getbands()
                has_alpha = "A" in bands or "transparency" in img.info
            entries.append(
                {
                    "file": path.name,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "format": fmt,
                    "width": width,
                    "height": height,
                    "mode": mode,
                    "has_alpha": bool(has_alpha),
                    "decodable": True,
                    "sha256": sha256_file(path),
                    "duplicate_group": None,
                    "content_hint": CONTENT_HINT.get(category, ""),
                    "match_candidate": path.stem,
                    "match_status": "exact_id",
                }
            )
    # 重复检测：同 sha256 归组（A-32 判据 7 要求 0 重复）
    by_sha = {}
    for row in entries:
        by_sha.setdefault(row["sha256"], []).append(row)
    for digest, group in by_sha.items():
        if len(group) > 1:
            for row in group:
                row["duplicate_group"] = digest[:12]

    INVENTORY_JSON.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY_JSON.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    return {
        "path": str(INVENTORY_JSON),
        "entries": len(entries),
        "by_category": {c: sum(1 for e in entries if Path(e["path"]).parent.name == c)
                        for c in CATEGORY_ORDER},
        "duplicate_groups": sum(1 for group in by_sha.values() if len(group) > 1),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="run5 photos JPEG→PNG 无损转码")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="只转前 N 张（调试用）")
    args = parser.parse_args(argv)

    found = scan()
    if found["other"]:
        print("[FAIL] 存在魔数未知的文件：%s" % [str(p) for _, p in found["other"]])
        return 1

    todo = found["jpeg"]
    if args.limit:
        todo = todo[: args.limit]
    print("[scan] jpeg=%d png=%d（其中角色真 PNG %d）"
          % (len(found["jpeg"]), len(found["png"]),
             sum(1 for c, _ in found["png"] if c == "role")))

    records = []
    failures = []
    started = time.time()
    for index, (category, path) in enumerate(todo, 1):
        try:
            record = transcode_one(path, category, args.dry_run)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            failures.append({"path": str(path), "error": "%s: %s" % (type(exc).__name__, exc)})
            print("[FAIL] %s -> %s" % (path.name, exc))
            continue
        records.append(record)
        if index % 20 == 0 or index == len(todo):
            print("[%3d/%3d] %s" % (index, len(todo), path.name))

    elapsed = time.time() - started
    if args.dry_run:
        print("[dry-run] 将转码 %d 张，备份到 %s" % (len(records), BACKUP_DIR))
        return 0 if not failures else 1

    inventory = write_inventory()
    manifest = {
        "schema": "run5_transcode_manifest/v1",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "operator": OPERATOR,
        "tool": {
            "python": sys.version.split()[0],
            "pillow": PIL.__version__,
            "encoder": 'PNG optimize=True（无量化、无调色板化、无缩放）',
        },
        "parameters": {
            "decode": 'Image.open -> load -> convert("RGB")',
            "resize": "none",
            "crop": "none",
            "rotate": "none",
            "quantize": "none",
            "backup_ext": ".jpg",
        },
        "summary": {
            "transcoded": len(records),
            "failures": len(failures),
            "elapsed_seconds": round(elapsed, 3),
            "source_bytes": sum(r["source_bytes"] for r in records),
            "output_bytes": sum(r["bytes"] for r in records),
            "pixel_equal_all": all(r["pixel_equality"]["equal"] for r in records),
            "max_diff_all": max((r["pixel_equality"]["max_diff"] for r in records), default=0),
            "by_category": {
                category: sum(1 for r in records if r["category"] == category)
                for category in CATEGORY_ORDER
            },
        },
        "inventory": inventory,
        "records": records,
        "failures": failures,
    }
    MANIFEST_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

    print("[manifest] %s" % MANIFEST_JSON)
    print("[inventory] %s（%d 条）" % (INVENTORY_JSON, inventory["entries"]))
    print("[summary] 转码 %d 张 / 失败 %d / 像素 max diff=%d / 体积 %.1f MiB -> %.1f MiB"
          % (len(records), len(failures), manifest["summary"]["max_diff_all"],
             manifest["summary"]["source_bytes"] / 1048576.0,
             manifest["summary"]["output_bytes"] / 1048576.0))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
