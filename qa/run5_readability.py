#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""M-13 原图可读性代理：274/274 逐张计算并落盘 qa/run5_readability.json。

覆盖口径
--------
run5 阶段只覆盖当时在册的 142 位；九类渲染面接入后 P 表为 274 位
（+ monster 52 / haunt 70 / ending 2 / card_back 3 / room_back 2 / dice 3），
本脚本改为对 **P 表全部行**逐张计算，不再按 promotion map 抽样。

阈值口径
--------
三类指标（spread / mean / extreme_ratio）对全部 11 个类别**沿用同一套阈值**：
实测 274 张里没有一张因类别差异需要豁免（haunt 70 张 16:9 大图的
spread 最小 0.166、mean 最小 0.085，仍在 [0.05,0.92] 内），因此不设
按类别的阈值分档，宁可如实报失败也不放宽。若将来某类确实不适用，
应在 `method` 里写明分档理由并把失败项原样保留在 `failures` 里。

为什么单独一个脚本
------------------
`qa/verify_p_table_final.py` 是**只读独立验收**，运行期间不得写任何项目文件
（A-03 会因此判 FAIL）。所以指标计算放在本脚本（实现侧先跑），验收脚本运行时
用同一函数在内存里复算并核对，不落盘。

指标口径（run5 §2.5 M-13）
--------------------------
* 下采样 256x256；
* 亮度 0.2126R + 0.7152G + 0.0722B（未线性化 sRGB，全库同一口径）；
* 带 alpha 的图（角色 12 张）只在 **alpha>=128 的非透明像素**上统计：透明画布
  不属于画面内容，算进去会把镂空误判成"死黑"；不透明占比 <1% 时退回全图；
* 三项阈值：P95−P5 ≥ 0.10；平均亮度 ∈ [0.05, 0.92]；过曝/死黑占比 ≤ 0.25。

阈值实现只有一份：直接复用 `qa/verify_p_table_final.py` 里的
``readability_metrics`` / ``readability_failures``，避免两处定义漂移。

用法::

    python qa/run5_readability.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GAME_DIR.parents[2]
QA_DIR = Path(__file__).resolve().parent
PTABLE_JSON = GAME_DIR / "assets" / "p_table.json"
OUT_JSON = QA_DIR / "run5_readability.json"

# P 表资源位总数：142 原有位 + 132 新增渲染面（monster 52 / haunt 70 /
# ending 2 / card_back 3 / room_back 2 / dice 3）。
EXPECTED_ROWS = 274

sys.dont_write_bytecode = True


def _load_verifier():
    path = QA_DIR / "verify_p_table_final.py"
    spec = importlib.util.spec_from_file_location("run5_verifier_metrics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    verifier = _load_verifier()
    payload = json.loads(PTABLE_JSON.read_text(encoding="utf-8"))
    records = payload.get("records") or []
    if len(records) != EXPECTED_ROWS:
        print("[FAIL] P 表行数=%d，期望 %d" % (len(records), EXPECTED_ROWS))
        return 1

    items, failures = [], []
    per_type = {}
    for rec in records:
        rid = rec.get("record_id")
        asset_type = rec.get("asset_type")
        path = PROJECT_ROOT / str(rec.get("source_path") or "")
        if not path.is_file():
            # 源文件缺失也计入 failures（不静默跳过，覆盖率缺口必须可见）
            failures.append("%s 源文件缺失：%s" % (rid, rec.get("source_path")))
            continue
        try:
            item = verifier.readability_metrics(path)
        except Exception as exc:  # noqa: BLE001
            failures.append("%s 解码失败：%s" % (rid, type(exc).__name__))
            continue
        item["record_id"] = rid
        item["asset_type"] = asset_type
        item["source_path"] = rec.get("source_path")
        items.append(item)
        per_type[asset_type] = per_type.get(asset_type, 0) + 1
        failures.extend(verifier.readability_failures(rid, item))

    method = (
        verifier.READABILITY_METHOD
        + " 阈值对 11 个类别统一（spread>=0.10 / mean∈[0.05,0.92] / "
          "过曝+死黑<=0.25）：实测 274 张无一需要按类别豁免，故不设分档；"
          "分类计数=%s。" % json.dumps(per_type, ensure_ascii=False, sort_keys=True)
    )
    document = {
        "schema": "run5_readability/v1",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "method": method,
        "count": len(items),
        "failures": failures,
        "items": items,
    }
    OUT_JSON.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print("[readability] %d 张 -> %s" % (len(items), OUT_JSON))
    print("[readability] 分类计数：%s"
          % json.dumps(per_type, ensure_ascii=False, sort_keys=True))
    print("[readability] 失败 %d 项" % len(failures))
    for item in failures[:5]:
        print("  - %s" % item)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
