#!/usr/bin/env python
"""桌面端资源注册表：按 target_ref / record_id 解析运行时图片。

只依赖标准库（不 import tkinter，也不 import Pillow）：启动时只建索引，
图片尺寸由 p_table.json 的 runtime_specs 给出，校验时直接读 PNG 头，
不做解码，因此可以安全地在 UI 启动路径上使用。

用法::

    from asset_registry import AssetRegistry

    registry = AssetRegistry.load("assets/p_table.json")
    ref = registry.resolve("card:omen:omen_bite")
    ref.path           # 运行时绝对路径
    ref.availability   # partial / missing
    ref.runtime_status # ok / fallback / placeholder
    ref.width, ref.height
    ref.content_ref    # 溯源用：content.py:OMEN_CARDS#omen_bite
    registry.missing()             # 47 个缺口
    registry.validate(assets_root) # 问题列表，不抛异常

键的分工（新旧键同时可解析，取图结果一致）
------------------------------------------
* ``target_ref``（规范溯源键，如 ``content.py:OMEN_CARDS#omen_bite``、
  ``content.py:CHARACTER_FACES#card_1@f0``）；
* ``runtime_key``（运行时键，如 ``card:omen:omen_bite`` / ``room:entrance_hall`` /
  ``character:card_1:f0``）；
* ``record_id``（``P-OMEN-001``）；
* ``content_ref``（content.py 原始记录 id，角色为 face id ``card_1_0``）；
* 裸 id（``omen_bite`` / ``entrance_hall`` / ``card_1_0`` / ``card_1#f0``）。

``resolve()`` 接受以上全部键形态（大小写不敏感）；``fallback_ref`` 仍存回退目标的
``record_id``（如 ``P-EVT-007``），``pending_missing`` 行留空。

健壮性约束（本轮补齐，均为显式拒绝而非静默兜底）
--------------------------------------------------
* 清单按 ``utf-8-sig`` 读取，带 BOM 的 JSON 也能加载；
* ``record_id`` / ``target_ref`` 任一重复即抛 ``ValueError``，不再 last-wins；
* 含路径分隔符或 ``..`` 的键不是合法解析键，``resolve`` 直接返回 ``None``。
"""

from __future__ import annotations

import json
import os
import re
import struct
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# asset_type -> runtime_specs 的键；卡牌（event/item/omen）共用 480x672。
SPEC_BY_TYPE = {
    "character": "character",
    "room": "room",
    "card_omen": "card",
    "card_item": "card",
    "card_event": "card",
}

CHARACTER_KEY_RE = re.compile(r"^(card_\d+)#f(\d+)$", re.IGNORECASE)
RECORD_ID_RE = re.compile(r"^P-(?:CHR|ROOM|OMEN|ITEM|EVT)-\d{3}$")


def png_size(path):
    """只读 PNG 头返回 (width, height)；非 PNG 或损坏返回 None。"""
    try:
        with open(str(path), "rb") as handle:
            head = handle.read(33)
    except OSError:
        return None
    if not head.startswith(PNG_SIGNATURE) or head[12:16] != b"IHDR":
        return None
    try:
        width, height = struct.unpack(">II", head[16:24])
    except struct.error:  # 截断文件：长度字段不足 8 字节，按非 PNG 处理
        return None
    return int(width), int(height)


class AssetRef:
    """一个资源位的解析结果；同时支持属性访问与 dict 式访问。"""

    __slots__ = (
        "key",
        "target_ref",
        "runtime_key",
        "record_id",
        "asset_type",
        "rel_path",
        "path",
        "availability",
        "runtime_status",
        "runtime_format",
        "fallback_ref",
        "width",
        "height",
        "source_path",
        "missing_note",
        "usable_fields",
        "quality_flags",
        "content_ref",
        "mapping_status",
    )

    def __init__(self, **kwargs):
        for name in self.__slots__:
            setattr(self, name, kwargs.get(name))

    # dict 兼容层：调用方写 ref["path"] 也能工作
    def __getitem__(self, name):
        return getattr(self, name)

    def get(self, name, default=None):
        return getattr(self, name, default)

    def keys(self):
        return list(self.__slots__)

    def to_dict(self):
        return {name: getattr(self, name) for name in self.__slots__}

    def exists(self):
        return bool(self.path) and os.path.isfile(self.path)

    @property
    def is_missing(self):
        return self.availability == "missing"

    @property
    def is_placeholder(self):
        return self.runtime_status == "placeholder"

    def __repr__(self):
        return "<AssetRef %s %s %s>" % (self.target_ref, self.availability,
                                        self.runtime_status)

    def __bool__(self):
        # 未解析到的引用为假值，便于 `if not registry.resolve(key)` 判断
        return self.record_id is not None


def default_manifest_candidates() -> list:
    """资源清单的候选路径，按优先级排列。

    源码运行：``<game>/assets/asset_mapping.json``。
    冻结包（PyInstaller）：assets 以 ``source/desktop/game/assets`` 结构内嵌到
    ``sys._MEIPASS``，而代码模块位于 ``_MEIPASS/game``，因此需要沿祖先回溯匹配。
    返回的列表由调用方取第一个存在的文件。
    """
    here = Path(__file__).resolve().parent
    candidates = [here / "assets" / "asset_mapping.json"]
    for parent in list(here.parents)[:6]:
        candidates.append(
            parent / "source" / "desktop" / "game" / "assets" / "asset_mapping.json")
    return candidates


def resolve_manifest_path() -> Path:
    """返回实际存在的资源清单路径；都不存在时返回首个候选（由调用方判定缺失）。"""
    candidates = default_manifest_candidates()
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


class AssetRegistry:
    """P 表 -> 运行时索引。"""

    def __init__(self, records, runtime_specs, base_dir_name, project_root,
                 manifest_path, generated_at="", stats=None):
        self.records = records
        self.runtime_specs = runtime_specs or {}
        self.base_dir_name = base_dir_name
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.manifest_path = Path(manifest_path) if manifest_path else None
        self.generated_at = generated_at
        self.stats = stats or {}

        self._refs = {}
        self._lower = {}
        self._id_index = {}
        self._content_index = {}
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("P 表记录必须是对象：%r" % (record,))
            ref = self._make_ref(record)
            self._register_key(ref.target_ref, ref)
            # runtime_key 是新旧键并存的运行时入口；旧表没有该列时为空，不注册。
            self._register_key(ref.runtime_key, ref)
            self._register_key(ref.record_id, ref)

    def _register_key(self, key, ref):
        """注册解析键；重复键直接失败，避免后者静默覆盖前者。"""
        if not key:
            return
        existing = self._refs.get(key)
        if existing is not None and existing is not ref:
            raise ValueError(
                "重复的解析键 %r：%s 与 %s 不能共用"
                % (key, existing.record_id, ref.record_id)
            )
        self._refs[key] = ref

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------
    def _spec_for(self, asset_type):
        key = SPEC_BY_TYPE.get(asset_type, "card")
        spec = self.runtime_specs.get(key, {"width": 0, "height": 0, "format": "png"})
        return spec

    def _make_ref(self, record):
        spec = self._spec_for(record.get("asset_type"))
        rel_path = record.get("runtime_path") or ""
        absolute = str(self.project_root / rel_path) if rel_path else ""
        return AssetRef(
            key=record.get("target_ref"),
            target_ref=record.get("target_ref"),
            runtime_key=record.get("runtime_key") or "",
            record_id=record.get("record_id"),
            asset_type=record.get("asset_type"),
            rel_path=rel_path,
            path=absolute,
            availability=record.get("availability"),
            runtime_status=record.get("runtime_status") or "placeholder",
            runtime_format=record.get("runtime_format") or spec.get("format", "png"),
            fallback_ref=record.get("fallback_ref") or "",
            width=int(spec.get("width") or 0),
            height=int(spec.get("height") or 0),
            source_path=record.get("source_path") or "",
            missing_note=record.get("missing_note") or "",
            usable_fields=record.get("usable_fields") or [],
            quality_flags=record.get("quality_flags") or [],
            content_ref=record.get("content_ref") or "",
            mapping_status=record.get("mapping_status") or "",
        )

    def _build_indexes(self, payload):
        """建立 小写键、content.py 引用、裸 id 三级索引（全部指向同一 AssetRef 键）。"""
        for key in list(self._refs):
            self._lower[key.lower()] = key

        # 内容侧入口：content_ref（content.py 原始记录 id，角色为 face id）
        for record in self.records:
            content_ref = str(record.get("content_ref") or "")
            if not content_ref.startswith("content.py:"):
                continue
            target_ref = str(record.get("target_ref") or "")
            self._content_index[content_ref.lower()] = target_ref
            content_id = content_ref.split("#")[-1]
            if content_id:
                self._id_index.setdefault(content_id, target_ref)

        # target_ref 的 id 段（角色为 card_1@f0，其余与 content_ref 的 id 相同）
        for record in self.records:
            target_ref = str(record.get("target_ref") or "")
            if not target_ref.startswith("content.py:") or "#" not in target_ref:
                continue
            target_id = target_ref.split("#", 1)[1]
            if target_id:
                self._id_index.setdefault(target_id, target_ref)

        # 兼容只带 content_refs 的清单（旧表/合成样本）：反向表 content.py: -> 运行时键
        content_refs = payload.get("content_refs") or {}
        for key, value in content_refs.items():
            if not key.startswith("content.py:"):
                continue  # 正向表（runtime_key -> content_ref）跳过
            lowered = key.lower()
            if lowered in self._content_index:
                continue
            runtime = str(value or "")
            ref = self._refs.get(runtime) or self._refs.get(runtime.lower())
            if ref is not None and ref.target_ref:
                self._content_index[lowered] = ref.target_ref
                bare = key.split("#")[-1]
                if bare:
                    self._id_index.setdefault(bare, ref.target_ref)

        # 裸 id：运行时键的最后一段（omen_bite / entrance_hall）
        for record in self.records:
            if record.get("asset_type") == "character":
                continue  # 角色已由 content_ref 的 face id 覆盖，避免 f0/f1 撞车
            runtime_key = str(record.get("runtime_key") or "")
            target_ref = str(record.get("target_ref") or "")
            if runtime_key:
                slot_id = runtime_key.split(":")[-1]
            elif target_ref and not target_ref.startswith("content.py:"):
                slot_id = target_ref.split(":")[-1]
            else:
                slot_id = ""
            if slot_id:
                self._id_index.setdefault(slot_id, target_ref or runtime_key)

    @classmethod
    def load(cls, path, base_dir=None):
        """读取 p_table.json（也接受 asset_mapping.json，自动找同目录 P 表）。"""
        manifest = Path(path)
        if not manifest.is_file():
            raise FileNotFoundError("找不到资源清单：%s" % manifest)

        # utf-8-sig：带 BOM 的清单（Excel/记事本另存常见）也能读取
        with manifest.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)

        if "records" not in payload:
            sibling = manifest.parent / "p_table.json"
            if sibling.is_file() and sibling.resolve() != manifest.resolve():
                return cls.load(sibling, base_dir=base_dir)
            raise ValueError("清单缺少 records，且同目录无 p_table.json：%s" % manifest)

        project_root = cls._detect_project_root(manifest, payload.get("base_dir"), base_dir)
        registry = cls(
            records=payload["records"],
            runtime_specs=payload.get("runtime_specs") or {},
            base_dir_name=payload.get("base_dir") or "",
            project_root=project_root,
            manifest_path=manifest,
            generated_at=payload.get("generated_at", ""),
            stats=payload.get("stats") or {},
        )
        registry._build_indexes(payload)
        return registry

    @staticmethod
    def _detect_project_root(manifest, base_dir_name, base_dir):
        if base_dir is not None:
            return Path(base_dir).resolve()
        # p_table.json 位于 <root>/source/desktop/game/assets/，项目根 = 含 photos 的祖先
        assets_dir = manifest.resolve().parent
        ancestors = [assets_dir] + list(assets_dir.parents)
        for parent in ancestors[:8]:
            if (parent / "photos").is_dir():
                return parent
        # 打包（PyInstaller onefile/onedir）布局：photos 不随包分发，
        # 但 assets 以 source/desktop/game/assets 结构内嵌，据此确定项目根，
        # 保证 runtime_path（项目根相对）在冻结环境同样可解析。
        for parent in ancestors[:8]:
            if (parent / "source" / "desktop" / "game" / "assets").is_dir():
                return parent
        if base_dir_name:
            for parent in ancestors[:8]:
                if parent.name == base_dir_name:
                    return parent
        return ancestors[4] if len(ancestors) > 4 else assets_dir

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def _normalize(self, key):
        if key is None:
            return None
        if not isinstance(key, str):
            key = str(key)
        text = key.strip()
        if not text:
            return None
        # 键空间不含路径分隔符；含 .. / / / \ 的键一律拒绝（防路径穿越探测）
        if ".." in text or "/" in text or "\\" in text:
            return None

        for candidate in (text, text.lower()):
            if candidate in self._refs:
                return candidate
            if candidate in self._lower:
                return self._lower[candidate]
            if candidate in self._content_index:
                return self._content_index[candidate]
            if candidate in self._id_index:
                return self._id_index[candidate]

        match = CHARACTER_KEY_RE.match(text)
        if match:
            target = "character:%s:f%s" % (match.group(1).lower(), match.group(2))
            return target if target in self._refs else None

        # content.py:CHARACTER_FACES#card_1（未带面别）无法唯一确定，明确返回 None
        return None

    def resolve(self, key):
        """按 target_ref / record_id / content.py 引用 / 裸 id 解析；未命中返回 None。"""
        normalized = self._normalize(key)
        if normalized is None:
            return None
        return self._refs.get(normalized)

    get = resolve

    def __contains__(self, key):
        return self.resolve(key) is not None

    def __len__(self):
        return len({id(ref) for ref in self._refs.values()})

    def __iter__(self):
        seen = set()
        for ref in self._refs.values():
            if id(ref) in seen:
                continue
            seen.add(id(ref))
            yield ref

    def target_refs(self):
        return [record["target_ref"] for record in self.records]

    def record_ids(self):
        return [record["record_id"] for record in self.records]

    def missing(self):
        """全部 availability=missing 的资源位（含已回退与走占位图的）。"""
        return [ref for ref in self if ref.availability == "missing"]

    def by_type(self, asset_type):
        return [ref for ref in self if ref.asset_type == asset_type]

    def summary(self):
        counts = {}
        for ref in self:
            counts[ref.availability] = counts.get(ref.availability, 0) + 1
        runtime = {}
        for ref in self:
            runtime[ref.runtime_status] = runtime.get(ref.runtime_status, 0) + 1
        return {"records": len(self), "availability": counts, "runtime_status": runtime}

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def validate(self, assets_root=None):
        """逐项校验，返回问题列表（不抛异常，供启动日志与测试断言使用）。"""
        issues = []
        root = Path(assets_root).resolve() if assets_root else None

        def add(ref, code, detail, severity="error"):
            issues.append(
                {
                    "record_id": ref.record_id,
                    "target_ref": ref.target_ref,
                    "code": code,
                    "detail": detail,
                    "severity": severity,
                }
            )

        for ref in self:
            if not ref.path:
                add(ref, "runtime_path_missing", "runtime_path 为空")
                continue

            path = Path(ref.path)
            if not path.is_file():
                add(ref, "runtime_file_absent", "运行时文件不存在：%s" % ref.rel_path)
                continue

            if root is not None:
                try:
                    path.resolve().relative_to(root)
                except ValueError:
                    add(ref, "runtime_outside_assets_root",
                        "运行时文件不在 assets_root 内：%s" % ref.rel_path)

            size = png_size(path)
            if size is None:
                add(ref, "runtime_not_png", "文件不是有效 PNG：%s" % ref.rel_path)
            elif (ref.width, ref.height) != size:
                add(
                    ref,
                    "runtime_size_mismatch",
                    "尺寸 %dx%d 与规格 %dx%d 不一致"
                    % (size[0], size[1], ref.width, ref.height),
                )

            if ref.availability == "missing":
                if not ref.missing_note:
                    add(ref, "missing_note_absent", "missing 行缺少缺口说明")
                if ref.source_path:
                    add(ref, "missing_has_source", "missing 行不应带 source_path")
                if ref.fallback_ref and self.resolve(ref.fallback_ref) is None:
                    add(ref, "fallback_unresolved",
                        "fallback_ref 无法解析：%s" % ref.fallback_ref)
                if ref.fallback_ref and not RECORD_ID_RE.match(ref.fallback_ref):
                    add(ref, "fallback_not_record_id",
                        "fallback_ref 应为回退目标 record_id：%s" % ref.fallback_ref)
                if ref.mapping_status == "pending_missing" and ref.fallback_ref:
                    add(ref, "pending_missing_with_fallback",
                        "pending_missing 不应带 fallback_ref：%s" % ref.fallback_ref)
                if ref.mapping_status == "fallback" and not ref.fallback_ref:
                    add(ref, "fallback_mapping_without_ref",
                        "mapping_status=fallback 但 fallback_ref 为空")
                if ref.runtime_status == "placeholder" and "placeholders/" not in ref.rel_path:
                    add(ref, "placeholder_path_suspect",
                        "placeholder 未指向 placeholders 目录：%s" % ref.rel_path)
                if ref.runtime_status == "fallback" and not ref.fallback_ref:
                    add(ref, "fallback_without_ref", "回退行缺少 fallback_ref")

        return issues

    def __repr__(self):
        return "<AssetRegistry %d records from %s>" % (len(self), self.manifest_path)


def load_registry(path, base_dir=None):
    """便捷函数，等价于 AssetRegistry.load。"""
    return AssetRegistry.load(path, base_dir=base_dir)


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parent / "assets" / "p_table.json"
    )
    registry = load_registry(target)
    print("records: %d" % len(registry))
    print("summary:", json.dumps(registry.summary(), ensure_ascii=False))
    print("missing: %d" % len(registry.missing()))
    issues = registry.validate(Path(target).resolve().parent)
    print("issues: %d" % len(issues))
    for issue in issues[:10]:
        print("  ", issue)
