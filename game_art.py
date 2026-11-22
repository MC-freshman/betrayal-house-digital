#!/usr/bin/env python
"""对局侧统一取图入口：资源键换算 / 尺寸缩放 / PhotoImage 强引用 / 渲染账本。

设计约束
--------
* **键换算集中**：调用方只给模型对象（``PlacedRoom`` / ``Card`` / ``CharacterFace``），
  由本模块换算成 P 表 ``runtime_key``：``room:<template_id>``、
  ``card:<kind>:<card_id>``、``character:<face.card_id>:f<face.face_index>``。
  注意 ``Player.character_id`` 是 **face id**（如 ``card_1_0``），不能直接拼键。
* **按尺寸记忆化**：``load_asset_photo`` 的缓存键含 ``max_size``，棋盘 tile 尺寸随窗口与
  zoom 连续变化，若每次都问绑定层就会反复解码。这里按 ``(kind, key, size)`` 再记一层，
  同尺寸重绘零解码。
* **强引用**：``ImageTk.PhotoImage`` 被 GC 回收时 ``__del__`` 会向 Tcl 发 ``image delete``，
  canvas 图元随即空白。本模块自持 dict（LRU 上限 ``PHOTO_MEMO_CAPACITY``）持有返回值；
  调用方仍需在自己的作用域内再持一次（棋盘每帧列表 / 对话框属性），因为 LRU 会在
  尺寸档切换时淘汰旧条目。
* **占位可观测**：``load_asset_photo`` 在文件缺失时会返回**占位图 PhotoImage 而不是 None**，
  所以这里先 ``registry.resolve`` 判可用性：资源位 ``is_missing`` / ``runtime_status != ok`` /
  文件不存在时**直接返回 None**，由调用方退回纯色块，并记 ``placeholder=True``。
  这样「是否退化成占位图」对探针是可机读的（fail-closed），也不会让 50 个房间
  全画同一张 room_missing。
* **只读资源**：不写 ``assets/``、不写 ``photos/``、不生成或转码任何图片。

用法::

    from game_art import get_shared

    art = get_shared()
    photo = art.photo("room", art.room_key(room.template_id), root, (ts, ts))
    if photo is None:
        ...  # 缺图：保留纯色矩形兜底
"""

from __future__ import annotations

import os
from collections import OrderedDict

try:  # 包内导入
    from . import ui_asset_binding
    from .asset_registry import AssetRegistry, resolve_manifest_path
except ImportError:  # pragma: no cover - 直接脚本执行
    import ui_asset_binding  # type: ignore
    from asset_registry import AssetRegistry, resolve_manifest_path  # type: ignore


# 渲染账本环形容量：探针只需要最近一帧，512 条足够覆盖 50 房 + 6 头像 + 若干弹窗。
LEDGER_CAPACITY = 512
# PhotoImage 记忆化上限。可按需调大，但必须保证调用方仍自持当前显示中的引用。
PHOTO_MEMO_CAPACITY = 256

ROOM_KIND = "room"
CARD_KIND = "card"
CHARACTER_KIND = "character"


def _normalize_size(size):
    """把 int / (w, h) 规整成 (w, h)；非法返回 None。"""
    if size is None:
        return None
    if isinstance(size, int):
        size = (size, size)
    try:
        width = int(size[0])
        height = int(size[1])
    except (TypeError, ValueError, IndexError):
        return None
    if width <= 0 or height <= 0:
        return None
    return (width, height)


def _face_parts(face):
    """从 CharacterFace / dict / (card_id, face_index) 里取 (card_id, face_index)。"""
    if face is None:
        return (None, None)
    if isinstance(face, (tuple, list)) and len(face) == 2:
        return (face[0], face[1])
    if isinstance(face, dict):
        return (face.get("card_id"), face.get("face_index"))
    return (getattr(face, "card_id", None), getattr(face, "face_index", None))


class GameArt:
    """对局侧取图器：唯一的 ``load_asset_photo`` 调用点 + 渲染账本。"""

    def __init__(self, registry=None, cache=None):
        # registry=None 表示懒加载（第一次真正取图时才读 manifest）。
        self._registry = registry
        self._registry_loaded = registry is not None
        self._cache = cache
        self._photos = OrderedDict()
        # 与 _photos 同键的溯源信息，命中时也要能记账（record_id/path）。
        self._meta = {}
        # PhotoImage 绑定到具体 Tk 解释器：master 一换（例如同进程内新建根窗口、
        # 或旧 root 已销毁），旧记忆化对象的 Tcl 名字已失效，复用会抛
        # ``TclError: image "pyimage1" doesn't exist``。这里用 id(master) 判换根。
        self._master_id = 0
        self._ledger = []
        self._counters = {
            "requests": 0,
            "misses": 0,
            "placeholder_hits": 0,
            "resolve_failures": 0,
            "loader_errors": 0,
        }

    # ------------------------------------------------------------------
    # 键换算（静态方法：不依赖实例状态，方便测试与相邻模块复用）
    # ------------------------------------------------------------------
    @staticmethod
    def room_key(template_id) -> str:
        """``PlacedRoom.template_id`` -> ``room:<template_id>``。

        不能用 ``room.key``（坐标键 ``0:0:0``）：registry.resolve 实测返回 None。
        """
        if not template_id:
            return ""
        return "room:%s" % str(template_id)

    @staticmethod
    def card_key(kind, card_id) -> str:
        """``Card.kind`` + ``Card.id`` -> ``card:<kind>:<card_id>``。"""
        if not kind or not card_id:
            return ""
        return "card:%s:%s" % (str(kind), str(card_id))

    @staticmethod
    def character_key(face) -> str:
        """``CharacterFace`` -> ``character:<card_id>:f<face_index>``。

        face 可以是 CharacterFace 对象、dict，或 ``(card_id, face_index)`` 二元组；
        取不到时返回空串（调用方据此退化为无头像）。
        """
        card_id, face_index = _face_parts(face)
        if not card_id or face_index is None:
            return ""
        try:
            index = int(face_index)
        except (TypeError, ValueError):
            return ""
        return "character:%s:f%d" % (str(card_id), index)

    # ------------------------------------------------------------------
    # 依赖（都是懒加载）
    # ------------------------------------------------------------------
    @property
    def registry(self):
        if not self._registry_loaded:
            self._registry_loaded = True
            try:
                manifest = resolve_manifest_path()
                if manifest is not None and os.path.isfile(str(manifest)):
                    self._registry = AssetRegistry.load(str(manifest))
            except Exception:
                self._registry = None
        return self._registry

    @property
    def cache(self):
        if self._cache is None:
            self._cache = ui_asset_binding.default_cache()
        return self._cache

    # ------------------------------------------------------------------
    # 取图
    # ------------------------------------------------------------------
    def photo(self, kind, key, master, size):
        """取一张 PhotoImage；缺图/未解析/占位一律返回 None（调用方退回纯色块）。

        kind: "room" | "card" | "character"（仅用于账本与调用点标记）
        key: 本模块 room_key/card_key/character_key 的产物
        master: 建议固定传同一个根窗口，保证绑定层缓存键里的 id(master) 稳定
        size: int 或 (w, h)，等比缩到该包围盒内（只缩不放）
        """
        size = _normalize_size(size)
        if not key or size is None:
            return None

        # master 一变，旧 PhotoImage 的 Tcl 名字已失效（旧 root 被销毁时最典型）。
        # 必须整批丢弃，否则 create_image 会抛 "image pyimageN doesn't exist"。
        master_id = id(master) if master is not None else 0
        if master_id != self._master_id:
            self.clear_photos()
            self._master_id = master_id

        memo_key = (kind, key, size, master_id)
        self._counters["requests"] += 1

        cached = self._photos.get(memo_key)
        if cached is not None:
            self._photos.move_to_end(memo_key)
            record_id, path = self._meta.get(memo_key, (None, None))
            # 命中也要记账：账本必须覆盖每一次取图，否则探针只能看到冷启动那一帧。
            self._record(kind, key, size, False, True, record_id, path)
            return cached

        self._counters["misses"] += 1

        registry = self.registry
        ref = registry.resolve(key) if registry is not None else None
        if ref is None:
            self._counters["resolve_failures"] += 1

        # 只有「资源位存在、状态 ok、文件在盘上」才算真图；否则视为占位。
        usable = bool(
            ref is not None
            and not ref.is_missing
            and (ref.runtime_status or "") == "ok"
            and ref.path
            and os.path.isfile(ref.path)
        )
        placeholder = not usable

        photo = None
        if usable:
            try:
                photo = ui_asset_binding.load_asset_photo(
                    registry, key, master, size, self.cache
                )
            except Exception:
                self._counters["loader_errors"] += 1
                photo = None
            if photo is None:
                placeholder = True

        self._record(
            kind,
            key,
            size,
            placeholder,
            ref is not None,
            getattr(ref, "record_id", None),
            getattr(ref, "path", None),
        )
        if photo is None:
            if placeholder:
                self._counters["placeholder_hits"] += 1
            return None

        self._photos[memo_key] = photo
        self._meta[memo_key] = (getattr(ref, "record_id", None), getattr(ref, "path", None))
        while len(self._photos) > PHOTO_MEMO_CAPACITY:
            stale, _value = self._photos.popitem(last=False)
            self._meta.pop(stale, None)
        return photo

    # ------------------------------------------------------------------
    # 账本
    # ------------------------------------------------------------------
    def _record(self, kind, key, size, placeholder, resolved, record_id, path) -> None:
        self._ledger.append(
            {
                "kind": kind,
                "key": key,
                "size": [size[0], size[1]],
                "placeholder": bool(placeholder),
                "resolved": bool(resolved),
                "record_id": record_id,
                "path": path,
            }
        )
        overflow = len(self._ledger) - LEDGER_CAPACITY
        if overflow > 0:
            del self._ledger[:overflow]

    def ledger(self):
        """渲染账本副本（每条含 kind/key/size/placeholder/resolved，另附 record_id/path）。"""
        return [dict(entry) for entry in self._ledger]

    def reset_ledger(self) -> None:
        """清空账本与计数（探针按帧取证用；不影响已记忆化的图片）。"""
        self._ledger.clear()
        for name in self._counters:
            self._counters[name] = 0

    def counters(self) -> dict:
        return dict(self._counters)

    def memo_size(self) -> int:
        return len(self._photos)

    def clear_photos(self) -> None:
        """丢弃记忆化的 PhotoImage（新开一局/切换 master 时用）。"""
        self._photos.clear()
        self._meta.clear()


_SHARED = None


def get_shared(registry=None) -> GameArt:
    """进程内单例：避免棋盘/面板/弹窗各自加载一遍注册表。"""
    global _SHARED
    if _SHARED is None:
        _SHARED = GameArt(registry)
    return _SHARED


def reset_shared() -> None:
    """清空单例（测试用；下次 get_shared 会重新懒加载）。"""
    global _SHARED
    _SHARED = None
