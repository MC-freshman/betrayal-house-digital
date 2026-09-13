# 山中小屋 · 电子版（非官方粉丝实现）

《山中小屋》（Betrayal at House on the Hill）的桌面电子版：Python 3.9 + tkinter，
**全部 70 本剧本**（含原版 1–50 与扩充 51–70）均有专属机制实现——令牌、怪物特殊规则、
逐步剧本行动、独立胜负判定与进度摘要，无通用兜底脚本。

## 功能

- 本地模式：单人 / 同屏热座，可加入机器人，4–6 人
- 机器人：三档难度 × 三种风格；带同源攻击合法性判定、集火、分散、护送揭示者等策略
- 联机：主机/客户端模式（局域网或 NATFRP 隧道），支持断线重连与联机存读档
- 内置规则、卡牌与房间图鉴、骰子结果展示

## 运行

需要带 tkinter 的 Python 3.9：

```bash
python launcher.py
```

## 测试

```bash
python replay_golden.py            # 185 条端到端种子回放（黄金基准）
python verify_haunt_systems.py     # 133 项剧本系统专项断言
python check_core_drift.py         # 双端规则内核单源校验
python verify_v1.py                # 桌面 UI 层回归（需 tkinter）
```

## 结构

```
game/            规则引擎、bot、桌面 UI、haunt handler 与剧本译文（本仓库根）
  haunts_zh/     70 本剧本玩家手册译文（Markdown）
  net/           联机协议与序列化
```

## 免责声明

本项目是爱好者制作的非官方粉丝实现，与 Avalon Hill / Wizards of the Coast 无任何关联，
也不是官方产品。剧本内容改编自原版桌游规则，仅供学习交流；请购买并支持正版桌游。
未随仓库分发任何官方规则书 PDF 或扫描图。仓库内容默认保留所有权利（All Rights Reserved），
未经许可请勿商用。
