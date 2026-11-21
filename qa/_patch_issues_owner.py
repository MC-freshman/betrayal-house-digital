#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一次性补丁：给 qa/run_p_table_execution.py 里仍然 open 的缺陷补
owner / closeCondition / reviewDate（A-25 要求 S3/S4 open 项必须带这三项）。"""

from pathlib import Path

PATH = Path(__file__).resolve().parent / "run_p_table_execution.py"

PAIRS = [
    ('"defectId": "PT-COV-001",',
     "qa / 独立验收人",
     "coverage.py 安装获批并在同一次运行产出 branch 计数",
     "2026-12-05"),
    ('"defectId": "PT-UI-001",',
     "product / UI 负责人",
     "有显示环境下的 100%/125%/150% 真实截图入库",
     "2026-12-05"),
    ('"defectId": "PT-SCOPE-001",',
     "product 负责人",
     "小程序端排期确认后单独立项",
     "2026-12-12"),
    ('"defectId": "PT-ART-002",',
     "素材复核人（非实现者）",
     "qa/run5_semantic_review.jsonl 47/47 签字 + 20 张 WCAG 采样",
     "2026-12-05"),
]


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    patched = 0
    for anchor, owner, close, review in PAIRS:
        start = text.find(anchor)
        if start < 0:
            print("[skip] 找不到 %s" % anchor)
            continue
        hint = text.find('"fixHint"', start)
        if hint < 0:
            print("[skip] %s 后无 fixHint" % anchor)
            continue
        if '"owner"' in text[start:hint]:
            print("[done] %s 已有 owner" % anchor)
            continue
        line_end = text.find("\n", hint)
        insert = ('\n        "owner": "%s",\n        "closeCondition": "%s",\n'
                  '        "reviewDate": "%s",' % (owner, close, review))
        text = text[:line_end] + insert + text[line_end:]
        patched += 1
    PATH.write_text(text, encoding="utf-8")
    print("[patch] %d 条缺陷补全 owner/closeCondition/reviewDate" % patched)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
