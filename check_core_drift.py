from __future__ import annotations

"""双端规则内核 · 同一性守门（M4 重写）。

M4 之后规则内核只有一份权威拷贝：本目录（桌面仓库的 `game` 包）。
后端 source/miniprogram/backend/app/game_core/ 不再持有代码拷贝，
而是一个把 `game.*` 注册为自身子模块的别名壳（见其 __init__.py）。

本守门因此从"文本 diff"升级为"同一性断言"，任何一边回潮都会失败：

    1. 权威侧必须存在全部内核模块；
    2. 后端 app/game_core/ 里除 __init__.py 外不得再出现 .py 拷贝；
    3. 后端别名壳导入的内核模块对象必须与本目录模块是**同一对象**
       （is 比较引擎/内容/模型/规则/中文名录/serialize 等）。

用法：
    python check_core_drift.py            # 守门检查（CI 阻断级）
退出码：0 通过 / 1 回潮。
"""

import importlib
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
BACKEND_APP = PROJECT_ROOT / "source" / "miniprogram" / "backend" / "app"

CORE_MODULES = [
    "bot_ai",
    "content",
    "engine",
    "models",
    "haunt_rules",
    "haunt_modes",
    "haunt_ai_profiles",
    "help_text",
    "haunts_zh",
]


def main() -> int:
    failures: list[str] = []

    # 0) 权威侧完整性
    for name in CORE_MODULES:
        if not (SCRIPT_DIR / f"{name}.py").is_file():
            failures.append(f"权威侧缺失模块：game/{name}.py")
    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        return 1

    # 1) 后端侧不得再有代码拷贝
    backend_core = BACKEND_APP / "game_core"
    if not backend_core.is_dir():
        failures.append(f"后端别名壳缺失：{backend_core}")
    else:
        strays = [f.name for f in backend_core.rglob("*.py") if f.name != "__init__.py"]
        if strays:
            failures.append(
                "后端 game_core 出现代码拷贝（必须是纯别名壳）：" + ", ".join(sorted(strays))
            )

    # 2) 同一性断言：后端导入的内核模块与本目录模块是同一对象
    if not failures:
        sys.path.insert(0, str(BACKEND_APP.parent))  # backend/
        try:
            for name in CORE_MODULES:
                backend_mod = importlib.import_module(f"app.game_core.{name}")
                desktop_mod = importlib.import_module(f"game.{name}")
                if backend_mod is not desktop_mod:
                    failures.append(f"{name}: 后端模块与桌面端不是同一对象（出现回潮拷贝）")
            backend_ser = importlib.import_module("app.game_core.net.serialize")
            desktop_ser = importlib.import_module("game.net.serialize")
            if backend_ser is not desktop_ser:
                failures.append("net.serialize: 后端与桌面端不是同一对象")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"后端别名壳导入失败：{exc}")

    if failures:
        print("[未通过] 双端内核同一性被破坏：")
        for f in failures:
            print(f"  - {f}")
        print("修复方向：删除后端拷贝、恢复 app/game_core/__init__.py 别名壳。")
        return 1

    print(
        "[通过] 双端规则内核单源成立："
        f"{len(CORE_MODULES)} 个内核模块 + net.serialize 均为同一对象；别名壳无拷贝。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
