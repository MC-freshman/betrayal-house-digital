"""Widow's Walk 新增资源位的 AI 美术占位管线（一次性工具）。

任务书第 16-18 条：image_gen 工具不可用时，用 Pillow 生成有类别标识的
占位图（深色底 + 类别文字 + 边框），确保 P 表 0 missing。本脚本做四件事：

1. 生成 50 张新增位源图写入 photos/（房间 20 → photos/room/、事件 15 →
   photos/event/、物品 10 → photos/item/、预兆 5 → photos/omen/），尺寸与
   现有源图口径一致（房间 2048x2048、卡牌 1773x2364），风格沿用
   asset_pipeline 的占位图配色（哥特深色底 + 金边 + 类别文字）。
2. 重导出旧 130 张 JPEG 魔数存 .png 的源图为真 PNG（验收 §1.2 partial→0，
   §1.3-3 允许 bytes/sha256 变化的同语义重导出）。
3. photos/role/ 12 张角色源图转 RGBA（验收 §4.2：角色位 has_alpha=true）。
4. 为 50 个新增位生成运行时占位图写入 assets/placeholders/（任务书第 13 条）。

用法：在 source/desktop/game 下 `python _gen_ww_art.py`。
"""
from __future__ import annotations

import sys
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GAME_DIR.parent.parent.parent  # Betrayal at House on the Hill/
PHOTOS_DIR = PROJECT_ROOT / "photos"
ASSETS_DIR = GAME_DIR / "assets"

if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

import asset_pipeline as ap  # noqa: E402  复用配色/字体/规格，避免两处定义漂移


ROOM_SRC = (2048, 2048)
CARD_SRC = (1773, 2364)

# 类别主题色（在统一深色底上微调，保证五类可辨识且低饱和）。
CATEGORY_ACCENT = {
    "room": ("#3a4a5e", "屋顶层 ROOM"),
    "event": ("#5e3a3a", "事件 EVENT"),
    "item": ("#4a5e3a", "物品 ITEM"),
    "omen": ("#4a3a5e", "预兆 OMEN"),
    "role": ("#5e523a", "角色 PORTRAIT"),
}


def make_category_art(path: Path, size: tuple, category: str, title: str, sub: str) -> Path:
    """深色底 + 类别文字 + 边框的 WW 占位美术（哥特低饱和）。"""
    from PIL import Image, ImageDraw

    width, height = size
    accent_hex, label_en = CATEGORY_ACCENT[category]
    bg = tuple(int(ap.COLOR_BG[i:i + 2], 16) for i in (1, 3, 5))
    panel = tuple(int(ap.COLOR_PANEL[i:i + 2], 16) for i in (1, 3, 5))
    accent = tuple(int(accent_hex[i:i + 2], 16) for i in (1, 3, 5))
    text = tuple(int(ap.COLOR_TEXT[i:i + 2], 16) for i in (1, 3, 5))
    muted = tuple(int(ap.COLOR_MUTED[i:i + 2], 16) for i in (1, 3, 5))
    border = tuple(int(ap.COLOR_BORDER[i:i + 2], 16) for i in (1, 3, 5))

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    inset = max(8, width // 28)
    draw.rectangle([inset, inset, width - 1 - inset, height - 1 - inset], fill=panel)
    draw.rectangle([inset, inset, width - 1 - inset, height - 1 - inset],
                   outline=border, width=max(3, width // 220))
    # 中部装饰横带（类别色），模拟卡面构图的中央主题区
    band_top = int(height * 0.30)
    band_bottom = int(height * 0.70)
    draw.rectangle([inset * 2, band_top, width - 1 - inset * 2, band_bottom],
                   fill=accent)
    draw.line([(inset * 2, band_top), (width - 1 - inset * 2, band_top)],
              fill=border, width=max(2, width // 400))
    draw.line([(inset * 2, band_bottom), (width - 1 - inset * 2, band_bottom)],
              fill=border, width=max(2, width // 400))

    font_title, cjk = ap._pick_font(max(24, width // 12), bold=True)
    font_sub, _ = ap._pick_font(max(14, width // 22), bold=True)
    font_note, _ = ap._pick_font(max(10, width // 34))

    ap._center_text(draw, (width / 2.0, height * 0.245), title if cjk else label_en,
                    font_title, text)
    ap._center_text(draw, (width / 2.0, height * 0.42), label_en, font_sub, border)
    ap._center_text(draw, (width / 2.0, height * 0.60), sub, font_sub, text)
    ap._center_text(draw, (width / 2.0, height * 0.80),
                    "WIDOW'S WALK · AI PLACEHOLDER ART", font_note, muted)
    ap._center_text(draw, (width / 2.0, height * 0.86),
                    "%dx%d" % (width, height), font_note, muted)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)
    return path


def _slots_by_family() -> dict[str, list[str]]:
    """返回 family -> 新增位 (id, 中文名) 列表，来自 content.py 的冻结集合。"""
    mod = ap.load_content()
    out: dict[str, list[tuple[str, str]]] = {}
    for room in mod.ROOF_ROOMS:
        out.setdefault("room", []).append((room["id"], room["name"]))
    for spec in mod.EVENT_SUPPLEMENTAL_SPECS[34:]:
        out.setdefault("event", []).append((spec[0], spec[1]))
    for card in mod.ITEM_CARDS:
        if card["id"] not in {
            "item_axe", "item_blood_dagger", "item_dynamite", "item_revolver",
            "item_sacrificial_dagger", "item_idol", "item_lucky_stone",
            "item_rabbit_foot", "item_healing_salve", "item_medical_kit",
            "item_smelling_salts", "item_adrenaline_shot", "item_angel_feather",
            "item_armor", "item_bell", "item_candle", "item_music_box",
            "item_bottle", "item_dark_dice", "item_amulet_of_the_ages",
            "item_pickpockets_gloves", "item_puzzle_box",
        }:
            out.setdefault("item", []).append((card["id"], card["name"]))
    for card in mod.OMEN_CARDS:
        if card["id"] not in {
            "omen_bite", "omen_book", "omen_crystal_ball", "omen_dog",
            "omen_girl", "omen_holy_symbol", "omen_madman", "omen_mask",
            "omen_medallion", "omen_ring", "omen_skull", "omen_spear",
            "omen_spirit_board",
        }:
            out.setdefault("omen", []).append((card["id"], card["name"]))
    return out


def generate_new_sources() -> dict:
    """任务 16-17：50 张新增位源图写入 photos/ 对应子目录。"""
    made = []
    photo_dir_by_family = {"room": "room", "event": "event", "item": "item", "omen": "omen"}
    size_by_family = {"room": ROOM_SRC, "event": CARD_SRC, "item": CARD_SRC, "omen": CARD_SRC}
    for family, items in _slots_by_family().items():
        for slot_id, name in items:
            path = PHOTOS_DIR / photo_dir_by_family[family] / f"{slot_id}.png"
            if path.is_file():
                continue
            make_category_art(path, size_by_family[family], family, name, slot_id)
            made.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
    return {"made": made, "count": len(made)}


def reexport_legacy_pngs() -> dict:
    """任务 18 / 验收 §1.2：旧 JPEG 魔数源图重导出真 PNG（photos/ 就地）。"""
    from PIL import Image

    reexported = 0
    for path in sorted(PHOTOS_DIR.rglob("*.png")):
        if path.parent.name == "role":
            continue  # 角色图已在格式上达标，下面单独处理 alpha
        with Image.open(path) as image:
            if image.format == "PNG":
                continue
            image.convert("RGB").save(path, format="PNG", optimize=True)
        reexported += 1
    return {"reexported": reexported}


def normalize_role_alpha() -> dict:
    """验收 §4.2：角色位 has_alpha=true —— photos/role/ 源图转 RGBA。"""
    from PIL import Image

    converted = 0
    for path in sorted((PHOTOS_DIR / "role").glob("*.png")):
        with Image.open(path) as image:
            if image.mode == "RGBA" and image.format == "PNG":
                continue
            image.convert("RGBA").save(path, format="PNG", optimize=True)
        converted += 1
    return {"rgba": converted}


def build_ww_runtime_placeholders() -> dict:
    """任务 13：为 50 个新增位生成运行时占位图（assets/placeholders/）。"""
    made = []
    for family, items in _slots_by_family().items():
        size = ap.ROOM_SIZE if family == "room" else ap.CARD_SIZE
        for slot_id, name in items:
            path = ASSETS_DIR / "placeholders" / f"ww_{family}_{slot_id}.png"
            if path.is_file():
                continue
            make_category_art(path, size, family, name, slot_id)
            made.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
    return {"made": made, "count": len(made)}


def main() -> int:
    new_sources = generate_new_sources()
    legacy = reexport_legacy_pngs()
    role = normalize_role_alpha()
    placeholders = build_ww_runtime_placeholders()
    print("photos/ 新增源图：%d 张" % new_sources["count"])
    for rel in new_sources["made"]:
        print("  +", rel)
    print("旧 JPEG 重导出真 PNG：%d 张" % legacy["reexported"])
    print("角色源图转 RGBA：%d 张" % role["rgba"])
    print("assets/placeholders/ WW 占位图：%d 张" % placeholders["count"])
    for rel in placeholders["made"][:5]:
        print("  +", rel)
    if placeholders["count"] > 5:
        print("  … 共 %d 张" % placeholders["count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
