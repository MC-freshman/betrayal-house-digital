"""全量黄金用例扫描：找出跑不完的用例（不看哈希，只看能不能收场）。

用法：在 source/desktop/game 下 `PYTHONIOENCODING=utf-8 python3 sweep_golden.py`。
与 replay_golden.py 的分工：replay 比"逐回合哈希与基准一致"（行为回归），
本脚本只统计"是否收场"（死局回归）。批次收口两个都要跑：
replay 绿 = 改动符合预期，sweep 的"新僵局 0 / 跑不完 0" = 没引入死局。
结果同时写到系统临时目录 sweep_result.json（可用 SWEEP_RESULT_FILE 覆盖），
供与上一版基准的 completed 对比。基准路径与 replay_golden.py 共用同一来源
（GOLDEN_BASELINE_FILE 环境变量可覆盖），保证两个脚本永远看同一份基准。
"""
import json, os, sys, tempfile
from pathlib import Path
import replay_golden as RG

baseline = {item["key"]: item for item in
            json.loads(RG.BASELINE_PATH.read_text(encoding="utf-8"))["cases"]}
rows = []
for seed, players, forced in RG.CASES:
    key = f"seed{seed}-{players}p" + (f"-haunt{forced}" if forced else "")
    try:
        cur = RG.run_case(seed, players, forced)
    except Exception as exc:
        rows.append({"key": key, "error": f"{type(exc).__name__}: {exc}"})
        print(f"[崩] {key}: {type(exc).__name__}: {exc}", flush=True)
        continue
    old = baseline.get(key, {})
    rows.append({
        "key": key, "turns": cur["turns"], "phase": cur["phase"],
        "winner": cur["winner"], "completed": cur["completed"],
        "haunt": cur["haunt"], "old_completed": old.get("completed"),
        "old_turns": old.get("turns"), "old_winner": old.get("winner"),
        "stalled_no_room_cards": cur["stalled_no_room_cards"],
    })
    flag = ""
    if not cur["completed"] and old.get("completed"):
        flag = "  <<< 新僵局"
    print(f"{key:24s} {cur['turns']:3d}回合 {cur['phase']:11s} {cur['winner'] or '-':7s} 剧本{cur['haunt']}{flag}", flush=True)
result_path = Path(os.environ.get("SWEEP_RESULT_FILE")
                   or Path(os.environ.get("TEMP", tempfile.gettempdir())) / "sweep_result.json")
result_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"结果已写入：{result_path}")
new_stalls = [r for r in rows if r.get("completed") is False and r.get("old_completed")]
print(f"\n用例 {len(rows)}，其中新僵局 {len(new_stalls)}: {[r['key'] for r in new_stalls]}")
old_stalls = [r for r in rows if r.get("completed") is False]
print(f"当前跑不完的用例 {len(old_stalls)}: {[r['key'] for r in old_stalls]}")
