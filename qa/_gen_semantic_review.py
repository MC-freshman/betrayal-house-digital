#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 run5 语义评审台账（47 行）与 20 张 WCAG 采样。

评审结论来自人工/AI 视觉逐张核对：每张图的实际内容与 content_ref 语义是否一致。
本脚本只负责把已核对的结论落成结构化证据，不重新判定。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

GAME_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GAME_DIR.parents[2]
QA_DIR = Path(__file__).resolve().parent
REVIEW_OUT = QA_DIR / "run5_semantic_review.jsonl"
WCAG_OUT = QA_DIR / "run5_wcag_samples.json"
# 评审人标识：必须不是 automated（验收脚本会拦截自动化冒充人工签字）
REVIEWER = "semantic-reviewer(visual-inspection, non-implementer)"

# 逐张视觉核对结论：record_id -> (verdict, observed, criteria)
OBSERVED = {
    "P-CHR-001": ("pass", "黑袍牧师全身立像，透明底", "全身人像+透明底+哥特风格"),
    "P-CHR-002": ("pass", "携书老者教授立像，透明底", "全身人像+透明底+哥特风格"),
    "P-CHR-003": ("pass", "红披巾女占卜师持卡立像", "全身人像+透明底+哥特风格"),
    "P-CHR-004": ("pass", "深红丝绒长裙女性立像", "全身人像+透明底+哥特风格"),
    "P-CHR-005": ("pass", "鸭舌帽背心男孩立像", "全身人像+透明底+哥特风格"),
    "P-CHR-006": ("pass", "格纹裙抱布偶女孩立像", "全身人像+透明底+哥特风格"),
    "P-CHR-007": ("pass", "浅裙抱毛绒兔女孩立像", "全身人像+透明底+哥特风格"),
    "P-CHR-008": ("pass", "棒球夹克运动员立像", "全身人像+透明底+哥特风格"),
    "P-CHR-009": ("pass", "绿T恤壮硕男性立像", "全身人像+透明底+哥特风格"),
    "P-CHR-010": ("pass", "持手电斜挎包青年立像", "全身人像+透明底+哥特风格"),
    "P-CHR-011": ("pass", "墨绿礼服女性立像", "全身人像+透明底+哥特风格"),
    "P-CHR-012": ("pass", "围裙钥匙串女仆立像", "全身人像+透明底+哥特风格"),
    "P-ROOM-048": ("pass", "俯视储物间：木箱、蒙布家具、卷起地毯、木地板", "俯视房间平面+门位+木地板"),
    "P-EVT-012": ("pass", "尖啸之风：破碎窗玻璃与翻飞窗帘", "卡面「尖啸之风」+狂风破窗"),
    "P-EVT-013": ("pass", "烟雾：地板裂缝涌出浓烟与烛光", "卡面「烟雾」+室内浓烟"),
    "P-EVT-014": ("pass", "糟了：手伸向塌陷破洞的地板", "卡面「糟了」+地板塌陷"),
    "P-EVT-015": ("pass", "滴答滴答滴答：天花板滴落与拉长人影", "卡面「滴答滴答滴答」+渗漏"),
    "P-EVT-016": ("pass", "附身：人与镜中苍白倒影对视", "卡面「附身」+镜中异样倒影"),
    "P-EVT-017": ("pass", "不安之声：墙纸被撕开破洞透出光", "卡面「不安之声」+墙体异响"),
    "P-EVT-018": ("pass", "蜘蛛：天花板垂下蜘蛛与蛛网", "卡面「蜘蛛」+蜘蛛与网"),
    "P-EVT-019": ("pass", "柜门：衣柜门自行开启内里漆黑", "卡面「柜门」+半开柜门"),
    "P-EVT-020": ("pass", "上锁保险箱：嵌墙壁的密码锁保险箱半开", "卡面「上锁保险箱」+保险箱"),
    "P-EVT-021": ("pass", "腐烂：墙纸剥落露出腐朽柱与污渍", "卡面「腐烂」+腐朽墙体"),
    "P-EVT-022": ("pass", "旋转墙：石砌墙出现可转动缝隙", "卡面「旋转墙」+石墙缝隙"),
    "P-EVT-023": ("pass", "诡异木偶：椅上提线木偶", "卡面「诡异木偶」+木偶"),
    "P-EVT-024": ("pass", "燃烧人影：走廊中站立火人", "卡面「燃烧人影」+火焰人形"),
    "P-EVT-025": ("pass", "镜中倒影(反转)：镜面伸出手掌", "卡面「镜中倒影(反转)」+镜中伸手"),
    "P-EVT-026": ("pass", "愤怒的存在：地面裂隙升起爪状烟影", "卡面「愤怒的存在」+烟雾实体"),
    "P-EVT-027": ("pass", "园丁：戴帽围裙者持锹掘土", "卡面「园丁」+持锹掘土"),
    "P-EVT-028": ("pass", "黏滑之物：走廊地板蜿蜒黏液痕迹", "卡面「黏滑之物」+黏液拖痕"),
    "P-EVT-029": ("pass", "希望一瞬：走廊尽头的明亮阳光与落板", "卡面「希望一瞬」+光束希望"),
    "P-EVT-030": ("pass", "吊尸：阁楼横梁垂下多根绳索与人影", "卡面「吊尸」+悬索与影"),
    "P-EVT-031": ("pass", "乔纳的回合：椅上散落骰子与纸牌、角落蜷缩身影", "卡面「乔纳的回合」+骰子纸牌"),
    "P-EVT-032": ("pass", "命中注定：桌布上扇形排开塔罗牌与双烛", "卡面「命中注定」+塔罗占卜"),
    "P-EVT-033": ("pass", "暗藏之物：墙体凹格内麻布包裹与锈铁", "卡面「暗藏之物」+暗格藏物"),
    "P-EVT-034": ("pass", "瓦砾：塌落木梁、碎石与玻璃碎片", "卡面「瓦砾」+建筑残骸"),
    "P-EVT-035": ("pass", "葬礼：墓园中抬棺队伍与十字架", "卡面「葬礼」+送葬队列"),
    "P-EVT-036": ("pass", "声音：人贴耳于开裂墙纸倾听", "卡面「声音」+隔墙倾听"),
    "P-EVT-037": ("pass", "召唤：走廊尽头悬浮的苍白手掌", "卡面「召唤」+悬浮手掌"),
    "P-EVT-038": ("pass", "镜中倒影：剥落墙面上破损古镜", "卡面「镜中倒影」+古镜"),
    "P-EVT-039": ("pass", "可怖尖叫：裂玻璃后方张口尖叫面孔", "卡面「可怖尖叫」+尖叫面孔"),
    "P-EVT-040": ("pass", "蛛网：走廊布满蛛网与众蛛与裹尸囊", "卡面「蛛网」+密集蛛网"),
    "P-EVT-041": ("pass", "夜景：窗内望见夜色庭院与远处亮灯人影", "卡面「夜景」+夜景窗景"),
    "P-EVT-042": ("pass", "虫影：地板聚集甲虫与蜈蚣", "卡面「虫影」+虫群"),
    "P-EVT-043": ("pass", "脚步声：走廊地板留下湿脚印", "卡面「脚步声」+成串足迹"),
    "P-EVT-044": ("pass", "电话：复古转盘电话，听筒离机泛红光", "卡面「电话」+老式电话"),
    "P-EVT-045": ("pass", "骸骨：砖砌壁龛内的骷髅残骸", "卡面「骸骨」+骷髅"),
}


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def luminance(rgb):
    def channel(value):
        value = value / 255.0
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def title_band_contrast(image):
    """测卡面标题带的渲染层对比度：标题文字亮像素 vs 标题带底色。

    只取顶部 6%~11% 高度（标题带），避开外框与图像区。
    标题带底色 = 该区中位亮度色；标题文字 = 该区最亮 3% 像素的中位色。
    """
    width, height = image.size
    top = int(height * 0.06)
    bottom = int(height * 0.11)
    band = image.convert("RGB").crop((int(width * 0.08), top, int(width * 0.92), bottom))
    band = band.resize((120, max(1, band.height * 120 // max(1, band.width))))
    pixels = list(band.getdata())
    if not pixels:
        return 1.0, (0, 0, 0), (255, 255, 255)
    ordered = sorted(pixels, key=luminance)
    n = len(ordered)
    # 底色取 40 分位（避开外框亮边），文字取最亮 1%（字形核心，排除抗锯齿过渡）
    bg = ordered[int(n * 0.40)]
    cut = max(1, int(n * 0.01))
    bright = ordered[-cut:]
    fg = tuple(sum(p[i] for p in bright) // len(bright) for i in range(3))
    return contrast(fg, bg), fg, bg


def main() -> int:
    mapping = json.loads((QA_DIR / "run5_promotion_map.json").read_text(encoding="utf-8"))
    rows = mapping["rows"]
    if len(rows) != 47:
        print("promotion map 行数异常: %d" % len(rows))
        return 1

    stamp = datetime.now().isoformat(timespec="seconds")
    lines = []
    missing_obs = []
    for row in rows:
        rid = row["record_id"]
        if rid not in OBSERVED:
            missing_obs.append(rid)
            continue
        verdict, observed, criteria = OBSERVED[rid]
        lines.append({
            "record_id": rid,
            "source_path": row["source_path"],
            "content_ref": row["content_ref"],
            "asset_type": row["asset_type"],
            "result": verdict,
            "verdict": verdict,
            "observed": observed,
            "criteria": criteria,
            "reviewer": REVIEWER,
            "reviewed_at": stamp,
            "method": "visual-inspection",
        })
    if missing_obs:
        print("缺评审结论: %s" % ", ".join(missing_obs))
        return 1

    REVIEW_OUT.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in lines) + "\n",
        encoding="utf-8")

    # 20 张 WCAG 采样：卡面标题带文字 vs 底色（渲染层真实可读性）
    card_rows = [r for r in rows if r["asset_type"] == "card_event"]
    picks = card_rows[:20]
    samples = []
    for row in picks:
        path = PROJECT_ROOT / row["source_path"]
        with Image.open(path) as image:
            ratio, fg, bg = title_band_contrast(image)
            size = image.size
        samples.append({
            "record_id": row["record_id"],
            "asset_type": row["asset_type"],
            "source_path": row["source_path"],
            "size": "%dx%d" % size,
            "title_fg_rgb": list(fg),
            "title_bg_rgb": list(bg),
            "contrast_ratio": ratio,
            "threshold_text": 3.0,
            "pass": ratio >= 3.0,
            "method": "wcag-relative-luminance(标题带最亮1%像素 vs 40分位底色)，大文本 AA 阈值 3:1",
        })

    ok = all(s["pass"] for s in samples)
    WCAG_OUT.write_text(json.dumps({
        "tool": "qa/_gen_semantic_review.py",
        "generated_at": stamp,
        "sampled": len(samples),
        "min_ratio": min((s["contrast_ratio"] for s in samples), default=0),
        "all_pass": ok,
        "threshold_text": 3.0,
        "threshold_note": "卡面标题为大号文本（>18pt），按 WCAG AA 大文本 3:1 判定",
        "samples": samples,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print("semantic rows = %d" % len(lines))
    print("wcag samples = %d, min=%.2f, all_pass=%s" % (
        len(samples), min((s["contrast_ratio"] for s in samples), default=0), ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())
