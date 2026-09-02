from __future__ import annotations

"""桌面端 / 小程序后端 · 规则内核漂移检测（M0-5 建成）

背景：规则内核曾复制成两份并在各自演化。8/31 审计时 haunt_rules.py 漂移
62.4%；9/2 实测已扩大到 4.4 倍字节差。在 M4（抽 game_core 共享包）落地之前，
用本脚本守住「不新增漂移」这条线，防止差距继续失控。

对比范围（两端规则内核的同名文件）：
    桌面端（权威，git 仓库在此）  source/desktop/game/
    后端                          source/miniprogram/backend/app/game_core/

判定（行级、忽略空白与空行）：
    · 漂移 > 该文件的上次基线   → 退出码 1（新增漂移，需要处理）
    · 漂移未超基线             → 放行（红色 ≠ 阻塞：合并前的已知差距）
    · --update                  → 把当前漂移记为基线
      桌面端每次改共享内核后、若不同步后端，应 --update 一次以示已知；
      M4 合并完成后漂移归零，此操作自然不再需要。

用法：
    python check_core_drift.py            # 检测
    python check_core_drift.py --update   # 记录当前状态为基线
    python check_core_drift.py --detail   # 顺带打印每个文件的前 5 处差异行
"""

import argparse
import difflib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
BACKEND_CORE = (
    PROJECT_ROOT / "source" / "miniprogram" / "backend" / "app" / "game_core"
)
BASELINE_FILE = SCRIPT_DIR / "core_drift_baseline.json"

# 两端规则内核的同名成对文件（9 对，与 8/31 审计口径一致）
SHARED_PAIRS = [
    "models.py",
    "content.py",
    "engine.py",
    "bot_ai.py",
    "haunt_rules.py",
    "haunt_ai_profiles.py",
    "help_text.py",
    "haunts_zh.py",
    "net/serialize.py",
]

# 桌面端已新增、后端还没有的内核文件 —— 属预期差异，M4 合并时补齐
DESKTOP_ONLY_CORE = ["haunt_modes.py"]


def norm_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def diff_line_count(desktop: Path, backend: Path) -> int:
    a, b = norm_lines(desktop), norm_lines(backend)
    if not a and not b:
        return 0
    # 行级忽略空白的对比：统计 unified diff 中被增删的行
    delta = list(
        difflib.unified_diff(
            a, b, fromfile=str(desktop), tofile=str(backend), lineterm="", n=0
        )
    )
    changed = [ln for ln in delta if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
    return len(changed)


def load_baseline() -> dict[str, int]:
    if BASELINE_FILE.is_file():
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    return {}


def save_baseline(data: dict[str, int]) -> None:
    BASELINE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="双端规则内核漂移检测")
    parser.add_argument("--update", action="store_true", help="把当前漂移记为基线")
    parser.add_argument("--detail", action="store_true", help="打印前 5 处差异行样例")
    args = parser.parse_args()

    if not BACKEND_CORE.is_dir():
        print(f"[错误] 找不到后端内核目录：{BACKEND_CORE}")
        return 2

    rows: list[dict] = []
    for rel in SHARED_PAIRS:
        desktop = SCRIPT_DIR / rel
        backend = BACKEND_CORE / rel
        if not desktop.is_file():
            print(f"[警告] 桌面端文件缺失：{rel}")
            continue
        if not backend.is_file():
            print(f"[警告] 后端文件缺失：{rel} —— 尚未从桌面端同步过来")
            continue
        rows.append(
            {
                "pair": rel,
                "current": diff_line_count(desktop, backend),
                "detail": args.detail,
            }
        )

    baseline = load_baseline()

    if args.update:
        data = {r["pair"]: r["current"] for r in rows}
        save_baseline(data)
        print("已把当前漂移记为基线：")
        for rel, n in data.items():
            print(f"  {rel:<22} {n} 差异行")
        return 0

    # 报告
    print(f"{'文件':<24}{'当前差异行':>10}{'上次基线':>10}{'较基线':>8}")
    regressed = []
    for r in rows:
        cur = r["current"]
        base = baseline.get(r["pair"], 0)
        delta = cur - base
        flag = "← 新增" if delta > 0 else ""
        print(f"{r['pair']:<24}{cur:>10}{base:>10}{delta:>+8}  {flag}")
        if delta > 0:
            regressed.append((r["pair"], cur, base))

    missing = [rel for rel in DESKTOP_ONLY_CORE if not (BACKEND_CORE / rel).is_file()]
    if missing:
        print("\n桌面端新增、后端缺失（M4 合并时补齐）：")
        for rel in missing:
            print(f"  {rel}")

    print(f"\n基线文件：{BASELINE_FILE.name}"
          + ("（尚不存在，首次运行请 --update 建立）" if not baseline else ""))

    if regressed:
        print("\n[未通过] 以下文件出现新增漂移，需处理（改动是有意的就 --update 记录）：")
        for rel, cur, base in regressed:
            print(f"  {rel}: {cur} > 基线 {base}")
        return 1

    if rows and all(baseline.get(r["pair"], -1) >= 0 for r in rows):
        print("\n[通过] 所有文件均未超出上次基线。")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
