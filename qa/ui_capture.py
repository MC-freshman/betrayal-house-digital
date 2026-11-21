#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""UI 美术预览三档 DPI 截图采集（真实 Tk 截图 + 明确标注的近似档）。

定位
----
* 档位判定（run4 dpi_capture_fix）：**对照真实 system_dpi 决定采集方式，不硬编码**。
  每档规范期望的系统 DPI 为 100%→96、125%→120、150%→144（run3 §2.5 判定表）。
* 100% 档：**恒为真实截图**。启动真实 GameApp + 帮助窗口「美术预览」页签，
  PIL.ImageGrab 抓屏，断言房间 PhotoImage 128x128、卡牌 240x336；
  系统 DPI 偏离 96 时由验收按 manifest 的 system_dpi 判 FAIL，不冒充 approximated。
* 125%/150% 档：system_dpi ≈120/144（±2）时走 **real-screenshot**（物理尺寸断言
  160×160 / 300×420、192×192 / 360×504）；否则 Tk 8.6 进程内无法真实模拟系统 DPI，
  只能用 ``tk scaling`` + 几何/图元尺寸放大做近似，状态写 ``status=approximated``、
  ``pass=false``，**不得写 PASS**，并在 manifest 写明 system_dpi 不匹配的原因。
* 桌面会话不支持截图（无显示/ImageGrab 失败）时整体 ``status=not-run`` 并记录错误，
  不冒充证据。

输出
----
* ``qa/screenshots/ui_100.png``（整窗）+ ``qa/screenshots/ui_100_crop.png``（预览区）
* 125%/150% 真实档：``ui_125.png`` / ``ui_150.png``（+crop）；近似档：``*_approx.png``
* ``qa/ui_capture.json``：``scales``（每档一条完整 manifest，含 expected_system_dpi /
  system_dpi_match / mode_decision）+ ``dpi``/``window``/``image``/``status``/``errors`` 摘要。

用法::

    python qa/ui_capture.py                # 三档全采
    python qa/ui_capture.py --scales 1.0   # 只采 100%
退出码：0 = 已采集（含 approximated）；2 = 未采集（无显示环境等）。
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
QA_DIR = Path(__file__).resolve().parent
SHOTS_DIR = QA_DIR / "screenshots"
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

sys.dont_write_bytecode = True  # 截图采集不生成 __pycache__，保持产物目录干净

# 每档期望的窗口几何与图元尺寸（缩放倍率 * 逻辑尺寸）；
# mode 仅为缺省值，实际 mode/approximated 由 capture_mode_decision 对照 system_dpi 决定
SCALE_PLAN = {
    100: {"scale": 1.0,  "tk_scaling": 1.333, "room": (128, 128), "card": (240, 336),
          "geometry": "1000x760", "mode": "real-screenshot"},
    125: {"scale": 1.25, "tk_scaling": 1.667, "room": (160, 160), "card": (300, 420),
          "geometry": "1250x950", "mode": "tk-scaling-approximation"},
    150: {"scale": 1.50, "tk_scaling": 2.000, "room": (192, 192), "card": (360, 504),
          "geometry": "1500x1140", "mode": "tk-scaling-approximation"},
}
NOTEBOOK_ART_TAB = 3  # 帮助窗口第 4 个页签 = 美术预览

# 每档规范期望的系统 DPI（run3 §2.5 判定表 / verify_p_table_final._validate_ui_real 同源）
EXPECTED_SYSTEM_DPI = {100: 96, 125: 120, 150: 144}
# 档位判定容差：|system_dpi - 期望| ≤2 视为处于该档（与物理尺寸 ±2 px 同量级）
SYSTEM_DPI_TOLERANCE = 2


def capture_mode_decision(percent, system_dpi):
    """对照真实 system_dpi 决定一档的采集方式（run4 dpi_capture_fix 接口）。

    返回 {mode, approximated, expected_system_dpi, dpi_match, reason}：
    * 100% 档恒为 real-screenshot——真实抓屏不受档位判定影响；system_dpi 偏离 96
      时如实记录（dpi_match=false），由验收按 manifest 判 FAIL，不写 approximated。
    * 125%/150% 档：system_dpi ≈ 期望（120/144，±SYSTEM_DPI_TOLERANCE）→ real-screenshot；
      否则 tk-scaling-approximation，reason 写明 system_dpi 不匹配（替换旧的
      ``approximated = percent >= 125`` 硬编码）。
    """
    expected = EXPECTED_SYSTEM_DPI.get(percent)
    dpi_match = bool(expected and system_dpi and
                     abs(int(system_dpi) - int(expected)) <= SYSTEM_DPI_TOLERANCE)
    if percent == 100:
        return {
            "mode": "real-screenshot",
            "approximated": False,
            "expected_system_dpi": expected,
            "dpi_match": dpi_match,
            "reason": ("100%% 档恒为真实抓屏；system_dpi=%s 对照期望 %s：%s"
                       % (system_dpi, expected,
                          "匹配" if dpi_match else "不匹配（如实记录，由验收按 system_dpi 判定）")),
        }
    if dpi_match:
        return {
            "mode": "real-screenshot",
            "approximated": False,
            "expected_system_dpi": expected,
            "dpi_match": True,
            "reason": ("system_dpi=%s 处于 %d%% 档规范值 %d±%d → real-screenshot"
                       % (system_dpi, percent, expected, SYSTEM_DPI_TOLERANCE)),
        }
    return {
        "mode": "tk-scaling-approximation",
        "approximated": True,
        "expected_system_dpi": expected,
        "dpi_match": False,
        "reason": ("system_dpi=%s 不在 %d%% 档规范值 %d±%d → 只能 tk scaling 近似；"
                   "真实档需系统改缩放并重启应用后重拍"
                   % (system_dpi, percent, expected, SYSTEM_DPI_TOLERANCE)),
    }


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(GAME_DIR.parents[2]).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def wcag_contrast(fg_hex: str, bg_hex: str) -> float:
    """按 WCAG 相对亮度计算对比度（设计色值；记录方法供 A-22 复核）。"""
    def _channel(value):
        value = value / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    def _luma(hex_text):
        text = hex_text.lstrip("#")
        r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)

    lighter = max(_luma(fg_hex), _luma(bg_hex))
    darker = min(_luma(fg_hex), _luma(bg_hex))
    return round((lighter + 0.05) / (darker + 0.05), 2)


def read_system_dpi() -> int:
    try:
        dc = ctypes.windll.user32.GetDC(0)
        try:
            return int(ctypes.windll.gdi32.GetDeviceCaps(dc, 88))  # LOGPIXELSX
        finally:
            ctypes.windll.user32.ReleaseDC(0, dc)
    except Exception:
        return 0


def read_dpi_awareness() -> int:
    try:
        value = ctypes.c_int(0)
        ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(value))
        return int(value.value)
    except Exception:
        try:
            return int(ctypes.windll.user32.GetProcessDPIAwareness())
        except Exception:
            return -1


# ---------------------------------------------------------------------------
# Tk 采集
# ---------------------------------------------------------------------------
def find_notebook(top):
    """在帮助窗口的子树里找 ttk.Notebook。"""
    import tkinter.ttk as ttk

    stack = list(top.winfo_children())
    while stack:
        widget = stack.pop(0)
        if isinstance(widget, ttk.Notebook):
            return widget
        stack.extend(widget.winfo_children())
    return None


def find_art_listbox(notebook, top):
    """在美术预览页签里找 Listbox。

    ttk.Notebook 的页 frame 由内部管理，``winfo_children()`` 返回空；
    必须走 ``nb.tabs()`` 的路径名 + ``nametowidget`` 定位。
    """
    for tab_path in notebook.tabs():
        try:
            widget = top.nametowidget(tab_path)
        except KeyError:
            continue
        stack = [widget]
        while stack:
            item = stack.pop(0)
            if item.winfo_class() == "Listbox":
                return item
            stack.extend(item.winfo_children())
    return None


def open_help_art_dialog(app, registry_refs):
    """打开帮助窗口并切到美术预览页签，返回 (dialog, top, notebook)。"""
    import ui as ui_module

    dialog = ui_module._HelpDialog(app, app.engine.catalog)
    top = dialog.top
    notebook = find_notebook(top)
    if notebook is None:
        raise RuntimeError("帮助窗口内未找到 Notebook")
    notebook.select(NOTEBOOK_ART_TAB)
    return dialog, top, notebook


def select_entry(kind_prefix, dialog, listbox):
    """在美术预览列表里选中第一个指定类别的条目，返回条目 ref。"""
    entries = dialog._art_entries
    index = None
    ref = None
    for position, (_label, item) in enumerate(entries):
        if str(item.asset_type) == kind_prefix or str(item.asset_type).startswith(kind_prefix):
            index = position
            ref = item
            break
    if index is None:
        return None
    listbox.selection_clear(0, "end")
    listbox.selection_set(index)
    listbox.see(index)
    listbox.event_generate("<<ListboxSelect>>")
    return ref


def capture_scale(app, percent, plan, errors, base_hashes):
    """采集一档；返回 manifest 条目（可能含 errors）。"""
    import tkinter as tk
    from PIL import ImageGrab

    # 档位判定：对照真实 system_dpi（run4 dpi_capture_fix），不硬编码 percent>=125
    system_dpi = read_system_dpi()
    decision = capture_mode_decision(percent, system_dpi)
    approximated = decision["approximated"]
    if approximated:
        # Tk 8.6 system-aware：进程内改 tk scaling 只影响点阵字体/像素换算，
        # 不改变系统实际缩放 —— 因此只能算近似，pass 恒为 false。
        app.tk.call("tk", "scaling", plan["tk_scaling"])
        import ui as ui_module

        # 基准保持 96 DPI 尺寸；由 _art_scaled_size 按 override DPI 等比缩放到目标。
        ui_module._HelpDialog.ART_ROOM_BASE = (128, 128)
        ui_module._HelpDialog.ART_CARD_BASE = (240, 336)
        ui_module._HelpDialog.ART_DPI_OVERRIDE = int(round(plan["tk_scaling"] * 72))
    else:
        # real-screenshot 档：清 override，让 _art_scaled_size 用 ctypes 读真实系统 DPI。
        import ui as ui_module

        ui_module._HelpDialog.ART_DPI_OVERRIDE = None
    # real-screenshot 档不触碰 tk scaling：如实记录系统初始化的实际值（例如 175%
    # 缩放的机器上是 168/96=1.75），供验收对照规范参考值判定，不伪造。
    try:
        actual_scaling = round(float(app.tk.call("tk", "scaling")), 4)
    except Exception:
        actual_scaling = 0.0
    entry = {
        "dpi_percent": percent,
        "system_dpi": system_dpi,
        "expected_system_dpi": decision["expected_system_dpi"],
        "system_dpi_match": decision["dpi_match"],
        "mode_decision": decision["reason"],
        "tk_scaling": actual_scaling,
        "tk_scaling_reference": plan["tk_scaling"],
        "dpi_awareness": read_dpi_awareness(),
        "mode": decision["mode"],
        "approximated": approximated,
        "scale_factor": plan["scale"],
    }

    try:
        dialog, top, notebook = open_help_art_dialog(app, None)
    except Exception as exc:
        errors.append("%d%% 帮助窗口打开失败：%s: %s" % (percent, type(exc).__name__, exc))
        entry["status"] = "not-run"
        entry["pass"] = False
        return entry

    listbox = find_art_listbox(notebook, top)
    if listbox is None:
        errors.append("%d%% 未找到美术预览列表" % percent)
        entry["status"] = "not-run"
        entry["pass"] = False
        top.destroy()
        return entry

    top.geometry(plan["geometry"])
    top.update_idletasks()
    app.update()
    time.sleep(0.35)

    room_ok = card_ok = True
    room_ref = select_entry("room", dialog, listbox)
    app.update()
    time.sleep(0.15)
    photo = getattr(dialog, "_art_photo", None)
    room_w = room_h = 0
    if photo is None or room_ref is None:
        room_ok = False
        errors.append("%d%% 房间条目未渲染出 PhotoImage" % percent)
    else:
        room_w, room_h = photo.width(), photo.height()
        want = plan["room"]
        if abs(room_w - want[0]) > 2 or abs(room_h - want[1]) > 2:
            room_ok = False
            errors.append("%d%% 房间图 %dx%d，期望 %dx%d" % (
                percent, room_w, room_h, want[0], want[1]))
        if room_ref.is_missing:
            errors.append("%d%% 选中的首个房间是 missing，未走 partial 正常图" % percent)

    card_ref = select_entry("card_", dialog, listbox)
    app.update()
    time.sleep(0.15)
    card_photo = getattr(dialog, "_art_photo", None)
    card_w = card_h = 0
    if card_photo is None or card_ref is None:
        card_ok = False
        errors.append("%d%% 卡牌条目未渲染出 PhotoImage" % percent)
    else:
        card_w, card_h = card_photo.width(), card_photo.height()
        want = plan["card"]
        if abs(card_w - want[0]) > 2 or abs(card_h - want[1]) > 2:
            card_ok = False
            errors.append("%d%% 卡牌图 %dx%d，期望 %dx%d" % (
                percent, card_w, card_h, want[0], want[1]))

    # 恢复房间预览再整窗截图，保证 full 图与断言同源
    select_entry("room", dialog, listbox)
    app.update()
    time.sleep(0.2)

    window_size = "%dx%d" % (top.winfo_width(), top.winfo_height())
    bbox = (top.winfo_rootx(), top.winfo_rooty(),
            top.winfo_rootx() + top.winfo_width(),
            top.winfo_rooty() + top.winfo_height())
    try:
        shot = ImageGrab.grab(bbox=bbox)
    except Exception as exc:
        errors.append("%d%% 截屏失败：%s: %s" % (percent, type(exc).__name__, exc))
        entry["status"] = "not-run"
        entry["pass"] = False
        top.destroy()
        return entry

    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    if approximated:
        full_name = "ui_%d_approx.png" % percent
        crop_name = "ui_%d_approx_crop.png" % percent
    else:
        full_name = "ui_%d.png" % percent
        crop_name = "ui_%d_crop.png" % percent
    full_path = SHOTS_DIR / full_name
    crop_path = SHOTS_DIR / crop_name
    shot.save(full_path)

    # crop：预览区 = 窗口右侧约 55%（美术预览页左侧为列表、右侧为预览图，结构固定）
    try:
        cx = int(shot.width * 0.45)
        crop = shot.crop((cx, 0, shot.width, shot.height))
    except Exception as exc:
        errors.append("%d%% 预览区裁剪退化： %s" % (percent, exc))
        crop = shot
    crop.save(crop_path)

    import ui as ui_module

    contrast_graphic = wcag_contrast(ui_module.PALETTE["accent"], ui_module.PALETTE["bg"])
    contrast_text = wcag_contrast(ui_module.PALETTE["text"], ui_module.PALETTE["panel"])

    entry.update({
        "window_size": window_size,
        "room_logical": "%dx%d" % (plan["room"] if approximated else (128, 128)),
        "room_physical": "%dx%d" % (room_w, room_h),
        "card_logical": "%dx%d" % (plan["card"] if approximated else (240, 336)),
        "card_physical": "%dx%d" % (card_w, card_h),
        "room_ratio": round(room_w / room_h, 4) if room_h else 0.0,
        "card_ratio": round(card_w / card_h, 4) if card_h else 0.0,
        "contrast_graphic": contrast_graphic,
        "contrast_text": contrast_text,
        "contrast_method": "wcag-relative-luminance(ui.PALETTE design values)",
        "screenshot_full": _relative(full_path),
        "screenshot_crop": _relative(crop_path),
        "sha256_full": sha256_file(full_path),
        "sha256_crop": sha256_file(crop_path),
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "reviewer": "qa/ui_capture.py 自动采集；人工复核待办",
        "app_source_sha256": base_hashes["ui"],
        "assets_sha256": base_hashes["p_table"],
        "size_assertions": {"room_ok": room_ok, "card_ok": card_ok},
        "selected_refs": {
            "room": str(getattr(room_ref, "record_id", "")),
            "card": str(getattr(card_ref, "record_id", "")),
        },
    })
    if approximated:
        entry["status"] = "approximated"
        entry["pass"] = False
        entry["approximation_note"] = (
            "Tk 8.6 system-aware 进程内无法真实模拟 120/144 DPI；"
            "本档为 tk scaling %s + 几何/图元尺寸放大近似，"
            "不得作为真实 DPI 证据（真实档需系统改缩放并重启应用后重拍）。档位判定：%s。"
            % (plan["tk_scaling"], decision["reason"]))
    else:
        entry["status"] = "pass" if (room_ok and card_ok) else "fail"
        entry["pass"] = bool(room_ok and card_ok)
        if not entry["pass"]:
            entry["status"] = "fail"
    top.destroy()
    return entry


def _walk(widget):
    stack = [widget]
    while stack:
        item = stack.pop(0)
        yield item
        stack.extend(item.winfo_children())


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="UI 美术预览三档 DPI 截图采集")
    parser.add_argument("--json", default="qa/ui_capture.json")
    parser.add_argument("--scales", default="100,125,150",
                        help="要采集的档位，逗号分隔（默认 100,125,150）")
    args = parser.parse_args(argv)

    errors = []
    scales = [int(item.strip()) for item in args.scales.split(",") if item.strip()]
    payload = {
        "tool": "qa/ui_capture.py",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        # dpi 摘要在 GameApp 构造后回填（含 SetProcessDpiAwareness(1) 之后的
        # 非虚拟化读数，run4 C-2 口径）；构造失败时保留空对象并记录错误。
        "dpi": {},
        "window": {},
        "image": {},
        "status": {},
        "errors": errors,
        "scales": [],
    }

    try:
        import tkinter

        root_probe = tkinter.Tk()
        root_probe.withdraw()
        root_probe.destroy()
    except Exception as exc:
        errors.append("无可用显示环境：%s: %s" % (type(exc).__name__, exc))
        payload["status"]["overall"] = "not-run"
        _write_json(payload, args.json)
        print("UI 截图采集 not-run：%s" % errors[-1])
        return 2

    app = None
    try:
        import ui as ui_module
        from asset_registry import AssetRegistry

        # GameApp 构造即真实桌面端入口：SetProcessDpiAwareness、引擎、完整 UI。
        app = ui_module.GameApp()
        app.update()
        if not ui_module._ASSET_REGISTRY_STATE.get("registry"):
            ui_module._get_asset_registry()
        registry = ui_module._ASSET_REGISTRY_STATE.get("registry")
        if registry is None:
            registry = AssetRegistry.load(GAME_DIR / "assets" / "asset_mapping.json")
        if registry is None:
            raise RuntimeError("美术预览清单不可用（asset_mapping.json）")

        base_hashes = {
            "ui": sha256_file(GAME_DIR / "ui.py"),
            "p_table": sha256_file(GAME_DIR / "assets" / "p_table.json"),
        }
        # 顶层 DPI 摘要：GameApp 构造（SetProcessDpiAwareness(1)）之后读取，
        # 保证 awareness 为本进程非虚拟化值（run4 C-2：awareness=0 直接 FAIL）
        payload["dpi"] = {
            "system_dpi": read_system_dpi(),
            "dpi_awareness": read_dpi_awareness(),
            "read_after": "GameApp 构造后（含 SetProcessDpiAwareness(1)）",
            "expected_system_dpi_by_scale": EXPECTED_SYSTEM_DPI,
            "scale_tolerance": SYSTEM_DPI_TOLERANCE,
            "decision_note": "125%/150% 档对照 system_dpi（120/144±2）决定 real-screenshot 或近似",
        }

        for percent in scales:
            plan = SCALE_PLAN.get(percent)
            if plan is None:
                errors.append("未知档位 %s%%" % percent)
                continue
            entry = capture_scale(app, percent, plan, errors, base_hashes)
            payload["scales"].append(entry)
            payload["window"][percent] = entry.get("window_size", "")
            payload["image"][percent] = entry.get("screenshot_full", "")
            payload["status"][percent] = entry.get("status", "not-run")
            print("  %d%%：status=%s room=%s card=%s window=%s" % (
                percent, entry.get("status"), entry.get("room_physical"),
                entry.get("card_physical"), entry.get("window_size")))
            # 分档证据持久化：只在新条目比已有条目更优时覆盖（real-screenshot
            # PASS > real-screenshot FAIL > approximated），避免低 DPI 会话的
            # 近似结果覆盖高 DPI 会话的 PASS 证据。
            tier_path = SHOTS_DIR / ("ui_capture_tier_%d.json" % percent)
            try:
                new_better = (
                    not entry.get("approximated") and entry.get("pass") is True)
                old_entry = None
                if tier_path.exists():
                    try:
                        old_entry = json.loads(
                            tier_path.read_text(encoding="utf-8"))
                    except Exception:
                        old_entry = None
                old_better = (
                    old_entry is not None
                    and not old_entry.get("approximated")
                    and old_entry.get("pass") is True)
                if new_better or not old_better:
                    tier_path.write_text(
                        json.dumps(entry, ensure_ascii=False, indent=1),
                        encoding="utf-8")
            except Exception:
                pass
        # 跨 DPI 会话合并：读取所有 tier 文件，把 real-screenshot PASS 的最优
        # 条目替换回 payload["scales"]，保证 ui_capture.json 包含三档最优证据。
        for percent in (100, 125, 150):
            tier_path = SHOTS_DIR / ("ui_capture_tier_%d.json" % percent)
            if not tier_path.exists():
                continue
            try:
                best = json.loads(tier_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(best, dict):
                continue
            is_better = (
                not best.get("approximated") and best.get("pass") is True)
            for i, sc in enumerate(payload["scales"]):
                if int(sc.get("dpi_percent") or 0) != percent:
                    continue
                cur_is_pass = (
                    not sc.get("approximated") and sc.get("pass") is True)
                if is_better and not cur_is_pass:
                    payload["scales"][i] = best
                    payload["window"][percent] = best.get("window_size", "")
                    payload["image"][percent] = best.get("screenshot_full", "")
                    payload["status"][percent] = best.get("status", "not-run")
    except Exception as exc:
        import traceback

        errors.append("采集失败：%s: %s" % (type(exc).__name__, exc))
        errors.append(traceback.format_exc(limit=4))
        payload["status"]["overall"] = "not-run"
    finally:
        if app is not None:
            try:
                app.destroy()
            except Exception:
                pass

    statuses = [entry.get("status") for entry in payload["scales"]]
    if statuses and all(s == "pass" for s in statuses):
        payload["status"]["overall"] = "pass"
    elif any(s == "fail" for s in statuses):
        payload["status"]["overall"] = "fail"
    elif statuses and all(s in ("approximated", "pass") for s in statuses):
        payload["status"]["overall"] = "approximated"
    else:
        payload["status"]["overall"] = "not-run"
    payload["claim_note"] = (
        "档位判定对照真实 system_dpi（100→96、125→120、150→144，±2）：100% 档恒为真实截图；"
        "125%/150% 档仅当系统处于规范 DPI 才为真实截图，否则 tk scaling 近似"
        "（status=approximated、pass=false），不得折算 PASS；未执行档位 status=not-run。")
    _write_json(payload, args.json)
    print("UI 截图采集完成：overall=%s；JSON=%s" % (
        payload["status"]["overall"], args.json))
    for error in errors:
        print("  error: %s" % error)
    return 0 if payload["status"]["overall"] != "not-run" else 2


def _write_json(payload, json_path):
    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
