#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一次性补丁：把 qa/run_p_table_execution.py 里残留的 95/47 旧口径文案
改成 run5 v2（142 usable / 0 missing）。只改文案，不改判定逻辑。"""

from pathlib import Path

PATH = Path(__file__).resolve().parent / "run_p_table_execution.py"

SUBS = [
    (
        '    lines.append("本轮未执行项不构成通过；`partial` 不等于 `usable`；"\n'
        '                 "47 个缺口仍为 missing/占位；分支覆盖未执行，不宣称达标。")',
        '    lines.append("本轮未执行项不构成通过；`usable` 不等于可发布；"\n'
        '                 "47 个缺口已落实为 0 missing / 142 usable；分支覆盖未执行，不宣称达标。")',
    ),
    (
        '                "95 partial / 47 missing 的真实标注、98 个运行时 PNG 与 UI 取图链路。"\n'
        '                "47 个美术缺口为内容积压，不在本 claim 范围；95 partial 不等于 usable。",',
        '                "142/142 usable 的真实标注、145 个运行时 PNG 与 UI 取图链路。"\n'
        '                "47 个美术缺口已在 run5 落实（复用 47 文件 + 130 张无损转码）；usable 不等于可发布。",',
    ),
    (
        '               "不得表述为发布级完成；47 个缺口为内容积压，不计入 usable。",',
        '               "不得表述为发布级完成；47 个缺口已落实，但语义评审与 WCAG 抽样仍未执行。",',
    ),
    (
        '                    "47 个美术缺口为内容积压，不是本次判定的原因（若 A-27 PASS）。",',
        '                    "47 个美术缺口已在 run5 落实；本次判定的阻断项与内容缺口无关。",',
    ),
    (
        '                       "47 个缺口保持 missing；claim 绑定产物哈希，任一关键产物变化即失效。"),',
        '                       "缺口已闭环为 0 missing；claim 绑定产物哈希，任一关键产物变化即失效。"),',
    ),
]


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    hits = 0
    for old, new in SUBS:
        if old not in text:
            print("[MISS] %r" % old[:70])
            continue
        text = text.replace(old, new, 1)
        hits += 1
    PATH.write_text(text, encoding="utf-8")
    print("[patch] %d/%d 处文案已更新" % (hits, len(SUBS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
