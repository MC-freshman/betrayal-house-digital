#!/usr/bin/env python
"""T-14：186 条黄金回放的漂移归因报告。

做三件事：

1. **跑**：按 ``replay_golden.CASES`` 逐条重跑，与 ``golden_replays.json`` 比对，
   记录 ``case_id / expected_hash / actual_hash / turns_diff / winner_diff / haunt_diff``
   （另附 phase_diff / completed_diff，便于判断是"换了胜负"还是"没跑到终局"）。
2. **归因**：按「变更批次」分组。批次取自远端仓库真实提交（本工作副本没有 git），
   每条用例归属到「第一个让它的终局哈希偏离 v3.7 的提交」。
3. **判读**：基线（2026-09-26）在远端历史里没有对应提交 —— 本脚本据此把用例分成
   「可归因到批次」与「基线不可复现」两类，后者必须显式列出，不允许算成通过。

为什么用 v3.7 当锚点而不是基线：基线快照的代码状态不在提交历史中（09-16 与 v3.7
两个提交分别回放都跑不回基线），拿基线做 bisect 起点只会得到"186 条全变"，
没有区分度。v3.7 之后的每个提交都是可运行的快照，因此能逐条定位到"从哪个批次开始变"。

用法::

    python qa/golden_drift_report.py                     # 跑当前树并出报告
    python qa/golden_drift_report.py --probe <ref> <out> # 在历史快照树里生成探针文件
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent
GAME_DIR = QA_DIR.parent
PROBE_DIR = QA_DIR / "golden_probes"
REPORT_PATH = QA_DIR / "golden_drift_report.json"

sys.path.insert(0, str(GAME_DIR))

import replay_golden  # noqa: E402

# 远端提交（gh api 实测，2026-11-24）：本工作副本无 .git，出处只能指向远端。
# layer 由该提交实际改到的文件路径判定：bot 决策层 = bot_ai.py / ai/* / haunt_ai_profiles.py；
# 规则层 = engine.py / engine_parts/* / rules/* / haunt_rules.py / haunts/* / haunt_table.py / content.py；
# 其它 = 资产、UI、qa、net 等。
REFS = [
    ("c3bf975f", "2026-10-09", "v3.7 剧本模块拆分（72 剧本文件）", ["规则层", "bot 决策层"]),
    ("da883af9", "2026-10-11", "v3.8 规则与 bot 目标精修", ["规则层", "bot 决策层"]),
    ("4c8466b3", "2026-10-12", "refactor: AI 与引擎规则模块化", ["规则层", "bot 决策层"]),
    ("391e2b98", "2026-10-12", "#67 目标链修复", ["规则层", "bot 决策层"]),
    ("133c9fe6", "2026-10-12", "#21 quest_carrier 持徽者优先", ["规则层"]),
    ("fcfea6f3", "2026-11-21", "v3.9 P 表 142 位 + 资产管线（36 剧本文件）", ["规则层"]),
    ("c018887a", "2026-11-22", "v3.10 美术接入 UI", ["其它"]),
    ("6b3fd92c", "2026-11-23", "v3.11 P 表 274 位 + 六类渲染面", ["规则层", "其它"]),
]

ANCHOR = "c3bf975f"          # 归因锚点：基线之后第一个可运行快照
BASELINE_DATE = "2026-09-26"


def _case_id(seed: int, players: int, forced) -> str:
    return "seed%d-%dp" % (seed, players) + ("-haunt%d" % forced if forced else "")


def _collect() -> dict:
    """跑完全部用例，返回 {key: 结果}。"""
    results = {}
    for seed, players, forced in replay_golden.CASES:
        key = _case_id(seed, players, forced)
        try:
            results[key] = replay_golden.run_case(seed, players, forced)
        except Exception as exc:  # 崩溃必须记账，不能当成"没差异"
            results[key] = {"error": "%s: %s" % (type(exc).__name__, exc)}
    return results


def _probe(ref: str, out: Path) -> int:
    payload = {"ref": ref, "cases": _collect()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("探针写出：%s（%d 条）" % (out, len(payload["cases"])))
    return 0


def _load_probes() -> dict:
    probes = {}
    if not PROBE_DIR.is_dir():
        return probes
    for path in sorted(PROBE_DIR.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ref = document.get("ref") or path.stem
        probes[ref] = document.get("cases") or {}
    return probes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="黄金回放漂移归因")
    parser.add_argument("--probe", nargs=2, metavar=("REF", "OUT"),
                        help="在历史快照树里生成探针文件（不写报告）")
    args = parser.parse_args(argv)

    if args.probe:
        return _probe(args.probe[0], Path(args.probe[1]))

    baseline = replay_golden.load_baseline()
    current = _collect()
    probes = _load_probes()

    rows = []
    for seed, players, forced in replay_golden.CASES:
        key = _case_id(seed, players, forced)
        now = current[key]
        want = baseline.get(key)
        expected_hash = (want or {}).get("hash", "")
        actual_hash = now.get("hash", "")
        row = {
            "case_id": key,
            "seed": seed,
            "players": players,
            "forced_haunt": forced,
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "drift": bool(expected_hash and actual_hash and expected_hash != actual_hash),
            "turns_diff": (now.get("turns") or 0) - (want or {}).get("turns", 0) if want else None,
            "winner_diff": (
                None if not want else
                ([want.get("winner"), now.get("winner")] if want.get("winner") != now.get("winner") else [])
            ),
            "haunt_diff": (
                None if not want else
                ([want.get("haunt"), now.get("haunt")] if want.get("haunt") != now.get("haunt") else [])
            ),
            "phase_diff": (
                None if not want else
                ([want.get("phase"), now.get("phase")] if want.get("phase") != now.get("phase") else [])
            ),
            "completed_diff": (
                None if not want else
                ([want.get("completed"), now.get("completed")]
                 if want.get("completed") != now.get("completed") else [])
            ),
            "error": now.get("error", ""),
        }
        rows.append(row)

    drift_rows = [row for row in rows if row["drift"] or row["error"]]

    # ---- 按批次归因 ----
    groups = {}
    details = {}
    for ref, date, label, layers in REFS:
        groups[ref] = {
            "commit": ref,
            "date": date,
            "label": label,
            "layers": layers,
            "cases": [],
        }
    groups["baseline_unreproducible"] = {
        "commit": "",
        "date": BASELINE_DATE,
        "label": "基线快照不可复现：v3.7 与当前表现一致，但都异于 2026-09-26 基线",
        "layers": ["基线快照（无对应提交）"],
        "cases": [],
    }

    unattributed = []
    for row in drift_rows:
        key = row["case_id"]
        anchor = (probes.get(ANCHOR) or {}).get(key, {})
        anchor_hash = anchor.get("hash", "")
        row["anchor_hash"] = anchor_hash
        if not anchor_hash:
            row["attribution"] = ""
            unattributed.append(key)
            continue
        if anchor_hash == row["actual_hash"]:
            row["attribution"] = "baseline_unreproducible"
            groups["baseline_unreproducible"]["cases"].append(key)
            continue
        hit = ""
        for ref, _date, _label, _layers in REFS:
            other = (probes.get(ref) or {}).get(key, {})
            if other.get("hash") and other["hash"] != anchor_hash:
                hit = ref
                break
        if hit:
            row["attribution"] = hit
            groups[hit]["cases"].append(key)
        else:
            row["attribution"] = ""
            unattributed.append(key)

    # ---- 连续批次矩阵：每一对相邻快照之间有多少条哈希变了 ----
    def signature(item: dict) -> tuple:
        """行为摘要（不含哈希）：哈希会被序列化载荷牵动，摘要不会。"""
        return (item.get("turns"), item.get("winner"), item.get("haunt"),
                item.get("phase"), item.get("completed"), item.get("monsters"),
                item.get("rooms"))

    chain = [(ref, probes.get(ref) or {}) for ref, _d, _l, _lay in REFS]
    chain.append(("current", current))
    step_matrix = []
    for (left_ref, left), (right_ref, right) in zip(chain, chain[1:]):
        hash_changed = 0
        sig_changed = 0
        compared = 0
        for row in rows:
            key = row["case_id"]
            a, b = left.get(key), right.get(key)
            if not a or not b or "hash" not in a or "hash" not in b:
                continue
            compared += 1
            if a["hash"] != b["hash"]:
                hash_changed += 1
            if signature(a) != signature(b):
                sig_changed += 1
        step_matrix.append({
            "from": left_ref,
            "to": right_ref,
            "compared": compared,
            "hash_changed": hash_changed,
            "behavior_signature_changed": sig_changed,
        })

    # ---- 每条用例：哪些批次动过它（相对前一个快照）----
    for row in drift_rows:
        key = row["case_id"]
        changed_at = []
        for step in step_matrix:
            left = dict(chain)[step["from"]].get(key, {})
            right = dict(chain)[step["to"]].get(key, {})
            if left.get("hash") and right.get("hash") and left["hash"] != right["hash"]:
                changed_at.append(step["to"])
        row["changed_at"] = changed_at

    by_winner = sum(1 for row in drift_rows if row["winner_diff"])
    by_haunt = sum(1 for row in drift_rows if row["haunt_diff"])
    by_phase = sum(1 for row in drift_rows if row["phase_diff"])
    only_turns = sum(1 for row in drift_rows
                     if not (row["winner_diff"] or row["haunt_diff"] or row["phase_diff"]))

    document = {
        "generated_by": "qa/golden_drift_report.py（只读：不改基准、不写 golden_replays.json）",
        "baseline": {
            "file": "golden_replays.json",
            "date": BASELINE_DATE,
            "cases": len(baseline),
        },
        "totals": {
            "cases": len(rows),
            "drifted": len(drift_rows),
            "matched": len(rows) - len(drift_rows),
            "winner_changed": by_winner,
            "haunt_changed": by_haunt,
            "phase_changed": by_phase,
            "turns_only": only_turns,
            "unattributed": len(unattributed),
        },
        "attribution_method": {
            "anchor": ANCHOR,
            "rule": "逐条比较「基线 vs 当前 vs 各历史快照」的终局哈希；"
                    "与 v3.7 相同 → 归入基线不可复现；与 v3.7 不同 → 归到第一个让哈希偏离的提交。",
            "why_not_baseline_bisect": "基线对应代码不在提交历史中：83cad5a7(09-16) 与 "
                                       "c3bf975f(v3.7) 分别回放都是 186/186 差异，"
                                       "以基线为起点无法区分批次。",
            "probes": sorted(probes.keys()),
        },
        "groups": [dict(**value, count=len(value["cases"])) for value in groups.values()],
        "step_matrix": step_matrix,
        "unattributed": unattributed,
        "cases": rows,
    }
    REPORT_PATH.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("黄金回放：%d 条，差异 %d 条，一致 %d 条"
          % (len(rows), len(drift_rows), len(rows) - len(drift_rows)))
    print("差异形态：换胜负 %d / 换剧本 %d / 换阶段 %d / 仅回合数 %d"
          % (by_winner, by_haunt, by_phase, only_turns))
    print("")
    for value in groups.values():
        print("  %-24s %-52s %d 条" % (value["commit"] or "-", value["label"][:50],
                                       len(value["cases"])))
    print("")
    print("连续批次矩阵（哈希变化 / 行为摘要变化）：")
    for step in step_matrix:
        print("  %-10s -> %-10s  %3d/%3d  /  %3d 条摘要变化"
              % (step["from"], step["to"], step["hash_changed"], step["compared"],
                 step["behavior_signature_changed"]))
    print("")
    print("未归因：%d 条%s" % (len(unattributed),
                            "" if not unattributed else " -> " + ", ".join(unattributed[:8])))
    print("写出 %s" % REPORT_PATH.relative_to(GAME_DIR).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
