from __future__ import annotations

"""桌面版发布包构建脚本。

之前 release/山中小屋.exe 是手工打包的，仓库里没有留下任何构建配置，
导致发布包一旦落后于源码就只能靠人肉记忆重建。本脚本把构建过程固化下来。

用法（必须用带 tkinter 的 Python 3.9，见下）：

    D:\\Various_programming_languages\\pycharm\\python3.9\\python.exe build_exe.py

可选参数：
    --check     只做环境与依赖检查，不真正构建
    --dist DIR  指定输出目录，默认写到项目根的 release/

为什么必须用 Python 3.9：
    PyInstaller 会把当前解释器的 tkinter 一起冻结进 EXE。用不带 tkinter
    的解释器（例如 managed Python 3.13）打包，产物能生成、但启动即崩，
    且 --windowed 模式下没有任何报错提示，很难排查。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
ENTRY = REPO / "launcher.py"
# REPO = …/source/desktop/game → 项目根需要上溯三级
PROJECT_ROOT = REPO.parents[2]
DEFAULT_DIST = PROJECT_ROOT / "release"
BUILD_DIR = REPO / "build"
APP_NAME = "山中小屋"


def _check(description: str, ok: bool, hint: str = "") -> bool:
    print(f"  [{'OK ' if ok else 'FAIL'}] {description}")
    if not ok and hint:
        print(f"         {hint}")
    return ok


def check_environment() -> bool:
    print("环境检查：")
    ok = True

    ok &= _check(
        f"Python {sys.version.split()[0]}",
        sys.version_info[:2] == (3, 9),
        "建议改用 D:\\Various_programming_languages\\pycharm\\python3.9\\python.exe",
    )

    try:
        import tkinter  # noqa: F401

        ok &= _check("tkinter 可用", True)
    except ModuleNotFoundError:
        ok &= _check("tkinter 可用", False, "该解释器没有 tkinter，打包出的 EXE 会启动即崩")
        return ok

    try:
        import PyInstaller  # noqa: F401

        ok &= _check(f"PyInstaller {PyInstaller.__version__}", True)
    except ModuleNotFoundError:
        ok &= _check("PyInstaller 可用", False, "运行：python -m pip install pyinstaller")
        return ok

    ok &= _check(f"入口脚本存在：{ENTRY.name}", ENTRY.is_file())
    return ok


def build(dist: Path) -> int:
    dist.mkdir(parents=True, exist_ok=True)
    # PyInstaller 的中间产物留在 build/，不要污染 release/
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(dist),
        "--workpath",
        str(BUILD_DIR / "work"),
        "--specpath",
        str(BUILD_DIR),
        str(ENTRY),
    ]

    print("\n开始构建（约 1-3 分钟）…")
    result = subprocess.run(command, cwd=str(REPO))
    if result.returncode != 0:
        print(f"\n构建失败，PyInstaller 退出码 {result.returncode}")
        return result.returncode

    exe = dist / f"{APP_NAME}.exe"
    if not exe.is_file():
        print(f"\n构建结束但找不到产物：{exe}")
        return 1

    size_mb = exe.stat().st_size / 1024 / 1024
    print(f"\n构建成功：{exe}（{size_mb:.1f} MB）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="构建山中小屋桌面版 EXE")
    parser.add_argument("--check", action="store_true", help="只做环境检查")
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST, help="输出目录")
    args = parser.parse_args()

    if not check_environment():
        print("\n环境检查未通过，已中止。")
        return 1

    if args.check:
        print("\n环境检查全部通过。")
        return 0

    return build(args.dist)


if __name__ == "__main__":
    raise SystemExit(main())
