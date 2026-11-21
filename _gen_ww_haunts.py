"""Widow's Walk 剧本（槽位 71-120）批量生成工具。

一次性生成四类产物（幂等，可重复运行）：
1. haunts/haunt_haunt71.py … haunt_haunt120.py：每本一个 mode handler
   模块（类 WWHauntNMode + 入口函数 haunt_hauntN）；
2. haunts/__init__.py 的 _MODULES / 类导入 / __all__ 追加；
3. haunts_zh/haunt_71.md … haunt_120.md：中文剧本手册（name + setup 文案，
   对照 ww_official_content.json 的 heroes_win / traitor_role 原文提炼）；
4. haunts_zh.py 的 HAUNT_TRANSLATIONS 追加 50 条（title_en/title_zh/hero/
   traitor 摘要）。

规则数据（rule_data）在 haunt_rules.py 的 _WW_SCENARIO_TABLE 手工维护，
本脚本不覆盖它——剧本规则与生成物分开演化。

用法：在 source/desktop/game 下 `python _gen_ww_haunts.py`。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent
CONTENT_JSON = GAME_DIR.parent.parent.parent / ".codebuddy" / "wfat" / "ww_official_content.json"

WW_SLOTS = list(range(71, 121))


def _official_haunts() -> dict[int, dict]:
    data = json.loads(CONTENT_JSON.read_text(encoding="utf-8"))
    out: dict[int, dict] = {}
    for item in data["haunts"]:
        if isinstance(item.get("id"), int) and item["id"] in WW_SLOTS:
            out[item["id"]] = item
    missing = set(WW_SLOTS) - set(out)
    if missing:
        raise SystemExit(f"ww_official_content.json 缺少剧本槽位：{sorted(missing)}")
    return out


def _hero_script(haunt: dict) -> str:
    return haunt.get("heroes_win") or "按官方英雄手册完成目标。"


def _traitor_script(haunt: dict) -> str:
    return haunt.get("traitor_role") or "按官方叛徒手册完成目标。"


def _trigger_text(haunt: dict) -> str:
    trigger = haunt.get("trigger") or {}
    rooms = "、".join(trigger.get("rooms") or [])
    omens = "、".join(trigger.get("omens") or [])
    condition = trigger.get("condition") or ""
    parts = []
    if rooms:
        parts.append(f"房间：{rooms}")
    if omens:
        parts.append(f"预兆：{omens}")
    if condition:
        parts.append(f"附加条件：{condition}")
    return "；".join(parts) or "（官方触发表未给出，见规则表）"


def _module_source(slot: int, haunt: dict) -> str:
    mode = f"ww_haunt_{slot}"
    class_name = f"WWHaunt{slot}Mode"
    func_name = f"haunt_haunt{slot}"
    name_en = haunt["name_en"].replace('"', "'")
    name_zh = haunt["name_zh"].replace('"', "'")
    official = haunt.get("official_id")
    author = haunt.get("author", "").replace('"', "'")
    hero = _hero_script(haunt).replace('"', "'")
    traitor = _traitor_script(haunt).replace('"', "'")
    return f'''"""WW 剧本 {slot}《{name_zh}》（{name_en}，官方 #{official}，作者 {author}）。

骨架剧本：双进度轨 + 检定型剧本行动（haunt_rules._WW_SCENARIO_TABLE[{slot}]）。
官方触发：{_trigger_text(haunt)}。
官方英雄胜利：{hero}
官方叛徒设定：{traitor}
引擎侧简化建模与官方差异逐条登记在 haunt_rules.py 的 engine_note。
"""
from __future__ import annotations

from typing import Any

from .base import GenericModeHandler


class {class_name}(GenericModeHandler):
    """剧本 {slot}「{name_en}」的 mode handler。

    行动与进度轨走 GenericModeHandler 的通用 rule_data 执行；这里只
    接管胜负判定的兜底分支：叛徒死亡 → 英雄立即获胜（官方剧本的通用
    击败线），其余条件交给 rule_data.win_conditions。
    """

    mode = "{mode}"

    def check_victory(self, engine: Any) -> bool:
        """剧本 {slot} 胜负判定：叛徒（traitor）死亡时英雄立即获胜。"""
        traitor_id = engine.state.traitor_id
        if traitor_id is not None:
            traitor = engine.state.players[traitor_id]
            if traitor.dead:
                engine._set_winner(
                    "heroes",
                    "叛徒被击败：{hero}",
                )
                return True
        return engine._check_generic_haunt_victory()

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        """进入作祟时执行剧本入口函数（校验胜负条件已就位）。"""
        {func_name}(engine)


def {func_name}(engine: Any) -> dict:
    """剧本 {slot} 的引擎入口：设置/校验叛徒与英雄的胜负条件。

    rule_data.win_conditions 在作祟初始化（engine._initialize_haunt_rules）
    时已写入 state.meta；这里显式校验两条胜负条件（hero / traitor）都在，
    返回给审计与测试断言。
    """
    rule = engine._generic_haunt_rule()
    conditions = rule.get("win_conditions") or []
    if not any(str(condition.get("winner")) == "heroes" for condition in conditions):
        raise RuntimeError("剧本 {slot} 缺少英雄胜负条件")
    if not any(str(condition.get("winner")) == "traitor" for condition in conditions):
        raise RuntimeError("剧本 {slot} 缺少叛徒胜负条件")
    return {{"win_conditions": conditions}}
'''


def _zh_md(slot: int, haunt: dict) -> str:
    name_zh = haunt.get("name_zh") or ""
    name_en = haunt.get("name_en") or ""
    official = haunt.get("official_id")
    author = haunt.get("author") or ""
    hero = _hero_script(haunt)
    traitor = _traitor_script(haunt)
    monsters = "、".join(haunt.get("monsters") or [])
    return f"""# #{slot} {name_zh}

原名：{name_en}（官方编号 {official}，作者 {author}）

## 触发

{_trigger_text(haunt)}

## 英雄手册

### 现在

预留若干属性检定令牌（三角形）。英雄目标轨道已由引擎建立：{hero}

### 你对坏人的了解

叛徒设定：{traitor}

### 获胜条件

{hero}

## 叛徒手册

### 现在

你的角色仍在游戏中，但已变为叛徒。按引擎叛徒轨道推进：{traitor}

### 获胜条件

{traitor}

## 引擎建模说明

本剧本为 Widow's Walk 骨架实现（skeleton）：双进度轨 + 检定型行动；
官方怪物：{monsters or '无独立怪物'}。
官方原文的简化建模与差异逐条登记在 haunt_rules.py 的 engine_note。
"""


def _append_haunts_init(slot: int, haunt: dict) -> None:
    path = GAME_DIR / "haunts" / "__init__.py"
    src = path.read_text(encoding="utf-8")
    module_name = f"haunt_haunt{slot}"
    class_name = f"WWHaunt{slot}Mode"
    changed = False
    if f'"{module_name}"' not in src:
        src = src.replace(
            '    "haunt_70_inhuman_transformation",\n]',
            '    "haunt_70_inhuman_transformation",\n' + "".join(
                f'    "haunt_haunt{sid}",\n' for sid in WW_SLOTS
            ) + "]",
        )
        changed = True
    if f"from .{module_name} import" not in src:
        src = src.replace(
            "from .haunt_70_inhuman_transformation import InhumanTransformationMode  # noqa: F401\n",
            "from .haunt_70_inhuman_transformation import InhumanTransformationMode  # noqa: F401\n"
            + "".join(
                f"from .haunt_haunt{sid} import WWHaunt{sid}Mode  # noqa: F401  WW {sid}\n"
                for sid in WW_SLOTS
            ),
        )
        changed = True
    if f'"{class_name}"' not in src:
        src = src.replace(
            "    \"ZombieTrapMode\",\n",
            "    \"ZombieTrapMode\",\n"
            + "".join(f'    "WWHaunt{sid}Mode",\n' for sid in WW_SLOTS),
        )
        changed = True
    if changed:
        path.write_text(src, encoding="utf-8")
        print(f"  haunts/__init__.py 已追加剧本 {slot} 的注册")


def _append_haunts_zh(entries: dict[str, dict]) -> None:
    path = GAME_DIR / "haunts_zh.py"
    src = path.read_text(encoding="utf-8")
    match = re.search(r"HAUNT_TRANSLATIONS = json\.loads\((.*)\)\s*$", src, re.S)
    if not match:
        raise SystemExit("haunts_zh.py 的格式与预期不符（找不到 json.loads(...)）")
    payload = json.loads(ast.literal_eval(match.group(1)))
    payload.update(entries)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    header = (
        "from __future__ import annotations\n\n"
        "import json\n\n"
        "# Auto-generated from BetrayalHouseHill_v4.2.pdf.\n"
        "# Do not edit by hand.\n"
        "# 2026-11-20：追加 Widow's Walk 剧本 71-120 的中文标题与手册摘要\n"
        "# （官方无中文版；对照 .codebuddy/wfat/ww_official_content.json 逐本提炼，\n"
        "# 由 _gen_ww_haunts.py 重新生成）。hero/traitor 字段为手册摘要而非全文。\n\n"
        f"HAUNT_TRANSLATIONS = json.loads({text!r})\n"
    )
    path.write_text(header, encoding="utf-8")
    print(f"  haunts_zh.py 已重写（{len(payload)} 本）")


def main() -> int:
    haunts = _official_haunts()
    made_modules = 0
    for slot in WW_SLOTS:
        haunt = haunts[slot]
        module_path = GAME_DIR / "haunts" / f"haunt_haunt{slot}.py"
        module_path.write_text(_module_source(slot, haunt), encoding="utf-8")
        made_modules += 1
        _append_haunts_init(slot, haunt)

        md_path = GAME_DIR / "haunts_zh" / f"haunt_{slot}.md"
        md_path.write_text(_zh_md(slot, haunt), encoding="utf-8")

    entries = {}
    for slot in WW_SLOTS:
        haunt = haunts[slot]
        entries[str(slot)] = {
            "title_en": haunt.get("name_en", ""),
            "title_zh": haunt.get("name_zh", ""),
            "hero": _zh_md(slot, haunt),
            "traitor": _traitor_script(haunt),
        }
    _append_haunts_zh(entries)
    print(f"完成：模块 {made_modules} 个、中文手册 50 份、翻译 50 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
