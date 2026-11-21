#!/usr/bin/env python
"""桌面 UI 取图层：按 asset_id 从 AssetRegistry 取运行时 PNG，带 LRU 缓存与占位回退。

设计约束
--------
* **懒 import tkinter**：模块顶层不 import tkinter，只有真正构造 ``PhotoImage``
  时才 import；因此无 Tk 的命令行/CI 环境仍可 import 本模块做静态检查。
* **不硬编码资源路径**：运行时文件路径全部来自 ``AssetRegistry``（``ref.path``）；
  占位图优先用 registry 里 ``runtime_status=placeholder`` 的行解析，
  其次用清单同目录的 ``placeholders/*.png`` 扫描，任一环节都拿不到才返回 ``None``。
* **缺图不崩**：未知键返回 ``None``；文件缺失或解码失败回落到占位图，
  失败次数记入 ``cache.errors``，调用方可观测。
* **LRU 缓存**：缓存键 = (资源键, 实际文件, max_size, master)，同图重复绑定
  不会重复解码；命中/未命中计数供 UI 性能项（PT-PERF-13）核对。

用法::

    from asset_registry import AssetRegistry
    from ui_asset_binding import load_asset_photo

    registry = AssetRegistry.load("assets/p_table.json")
    photo = load_asset_photo(registry, "room:entrance_hall", root, (256, 256))
    if photo is None:
        ...  # 连占位图都没有，UI 显示纯文本兜底

Python 3.9 可运行；Pillow 存在时用 ImageTk 精确缩放，缺失时退回 tkinter 整数降采样。
"""

from __future__ import annotations

import math
from collections import OrderedDict
from pathlib import Path

DEFAULT_MAX_SIZE = (256, 256)
DEFAULT_CACHE_CAPACITY = 64

# 内置占位图目录：run5 之后 142 位全部落实到真图，p_table 里已没有
# ``runtime_status=placeholder`` 的行，清单同目录也不一定有 placeholders/。
# 没有这一层，"坏图/缺图 → 占位图"的兜底会在临时清单下断掉。
GAME_DIR = Path(__file__).resolve().parent
DEFAULT_PLACEHOLDER_DIR = GAME_DIR / "assets" / "placeholders"

# 资源类别 -> 占位图种类（assets/placeholders/<kind>_missing.png 的 kind）
PLACEHOLDER_KIND_BY_TYPE = {
    "character": "character",
    "room": "room",
    "card_event": "event",
    "card_item": "event",
    "card_omen": "event",
}


# ----------------------------------------------------------------------
# 缓存
# ----------------------------------------------------------------------
class AssetImageCache:
    """按插入顺序淘汰的 LRU 缓存，附带命中/未命中/解码失败计数。"""

    def __init__(self, capacity: int = DEFAULT_CACHE_CAPACITY):
        self.capacity = max(1, int(capacity))
        self._items = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.errors = 0

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key) -> bool:
        return key in self._items

    def clear(self) -> None:
        self._items.clear()

    def get(self, key):
        if key in self._items:
            self._items.move_to_end(key)
            self.hits += 1
            return self._items[key]
        self.misses += 1
        return None

    def put(self, key, value):
        if key in self._items:
            self._items.move_to_end(key)
            self._items[key] = value
            return value
        self._items[key] = value
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)
            self.evictions += 1
        return value

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "capacity": self.capacity,
            "size": len(self._items),
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "errors": self.errors,
            "hit_rate": round(self.hits / float(total), 4) if total else 0.0,
        }


# 每个 Tk master 单独的默认缓存：PhotoImage 绑定解释器，不能跨 root 复用。
_DEFAULT_CACHES = {}


def default_cache(master=None) -> AssetImageCache:
    """取（或创建）某 master 的默认缓存；master=None 时用单独桶。"""
    key = id(master) if master is not None else 0
    cache = _DEFAULT_CACHES.get(key)
    if cache is None:
        cache = AssetImageCache()
        _DEFAULT_CACHES[key] = cache
    return cache


def reset_default_caches() -> None:
    """清空默认缓存表（测试或多窗口重建时使用）。"""
    _DEFAULT_CACHES.clear()


def cache_stats(master=None) -> dict:
    """默认缓存的命中统计，便于 UI 侧输出可观测指标。"""
    return default_cache(master).stats()


# ----------------------------------------------------------------------
# 路径与缩放
# ----------------------------------------------------------------------
def _existing(path) -> bool:
    import os

    return bool(path) and os.path.isfile(path)


def _placeholder_candidates(registry, asset_type) -> list:
    """占位图候选：优先 registry 自带 placeholder 行，其次扫描清单同目录。"""
    candidates = []
    if registry is not None:
        fallback_any = []
        for ref in registry:
            if ref.runtime_status != "placeholder" or not ref.path:
                continue
            fallback_any.append(ref.path)
            if ref.asset_type == asset_type:
                candidates.append(ref.path)
        if not candidates:
            candidates.extend(fallback_any)

    manifest = getattr(registry, "manifest_path", None)
    kind = PLACEHOLDER_KIND_BY_TYPE.get(asset_type, "")
    if manifest is not None:
        directory = manifest.parent / "placeholders"
        if directory.is_dir():
            names = sorted(p for p in directory.glob("*.png") if p.is_file())
            preferred = [p for p in names if kind and kind in p.name]
            candidates.extend(str(p) for p in preferred or names)

    # 最后一层：游戏自带的三张占位图（run5 起是唯一稳定来源）。
    if not candidates and kind:
        builtin = DEFAULT_PLACEHOLDER_DIR / ("%s_missing.png" % kind)
        if builtin.is_file():
            candidates.append(str(builtin))

    unique = []
    seen = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _fit_size(width: int, height: int, max_size) -> tuple:
    """等比缩到 max_size 内；尺寸非法返回 (0, 0)。"""
    if width <= 0 or height <= 0:
        return (0, 0)
    max_width = max(1, int(max_size[0]))
    max_height = max(1, int(max_size[1]))
    scale = min(1.0, max_width / float(width), max_height / float(height))
    return (max(1, int(round(width * scale))), max(1, int(round(height * scale))))


def _make_photo(path, master, max_size):
    """把一张 PNG 读成 PhotoImage；Pillow 可用时精确缩放，否则整数降采样。"""
    import tkinter

    try:
        from PIL import Image, ImageTk
    except ImportError:  # pragma: no cover - 有 Pillow 的环境不会走这里
        Image = None
        ImageTk = None

    if Image is not None and ImageTk is not None:
        with Image.open(path) as image:
            image.load()
            target = _fit_size(image.size[0], image.size[1], max_size)
            if target != (0, 0) and target != image.size:
                resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                image = image.resize(target, resample)
            return ImageTk.PhotoImage(image, master=master)

    photo = tkinter.PhotoImage(master=master, file=str(path))
    width, height = photo.width(), photo.height()
    target = _fit_size(width, height, max_size)
    if target == (0, 0):
        return photo
    factor = int(math.ceil(max(width / float(target[0]), height / float(target[1]))))
    if factor > 1:
        photo = photo.subsample(factor, factor)
    return photo


# ----------------------------------------------------------------------
# 对外入口
# ----------------------------------------------------------------------
def load_asset_photo(registry, key, master, max_size=DEFAULT_MAX_SIZE, cache=None):
    """按 asset_id / target_ref / record_id 取图，返回 PhotoImage 或 None。

    解析顺序：registry.resolve(key) -> ref.path -> 占位图。
    未知键返回 None；文件缺失或解码失败回落到占位图并记 errors。
    """
    cache = cache if cache is not None else default_cache(master)
    ref = registry.resolve(key) if registry is not None else None
    if ref is None:
        cache.misses += 1
        return None

    primary = ref.path if _existing(ref.path) else ""
    asset_type = ref.asset_type
    candidates = [primary] if primary else []
    candidates.extend(_placeholder_candidates(registry, asset_type))

    cache_key = (
        ref.record_id or ref.target_ref or str(key),
        primary,
        tuple(max_size),
        id(master),
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    for candidate in candidates:
        if not _existing(candidate):
            continue
        try:
            photo = _make_photo(candidate, master, max_size)
        except Exception:
            cache.errors += 1
            continue
        if photo is not None:
            return cache.put(cache_key, photo)
    return None


def load_photo_for_ref(ref, master, max_size=DEFAULT_MAX_SIZE, cache=None):
    """直接按 AssetRef 取图（已持有 ref、不想再解析键时使用）。"""
    if ref is None or not _existing(getattr(ref, "path", "")):
        return None
    cache = cache if cache is not None else default_cache(master)
    cache_key = (ref.record_id or ref.target_ref, ref.path, tuple(max_size), id(master))
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        photo = _make_photo(ref.path, master, max_size)
    except Exception:
        cache.errors += 1
        return None
    return cache.put(cache_key, photo)
